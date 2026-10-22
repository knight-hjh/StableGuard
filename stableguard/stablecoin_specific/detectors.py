"""C1-C5 / S01-S19 detectors (parallel to the 40-type extractors).

Each detector flags candidate locations for one sub-type. They are HIGH-RECALL
structural matchers (the LLM stage recovers precision in N4), built mostly on the
function's Solidity SOURCE TEXT (robust for these semantic signatures) plus light
slither structure (functions, contracts, source files).

Add a detector by decorating with @detector("Sxx"). The driver runs all of them.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, asdict
from typing import List, Callable, Optional

from loguru import logger
from slither.core.declarations import Contract, Function


@dataclass
class Candidate:
    sub: str                 # "S02"
    contract: str            # contract name
    file: str                # source file basename
    function: str            # function name
    line: int                # first line
    reason: str              # why it matched (for the prompt + triage)
    confidence: str = "low"  # low|medium (static prior only; LLM decides)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def src_file(contract: Contract) -> str:
    try:
        return os.path.basename(contract.source_mapping.filename.absolute)
    except (AttributeError, TypeError):
        return "unknown"


def fn_line(func: Function) -> int:
    try:
        return func.source_mapping.lines[0]
    except (AttributeError, IndexError, TypeError):
        return 0


def fn_file(func: Function) -> str:
    """The file where the function is DECLARED (an inherited fn lives in its base file,
    not the deriving contract's file). Falls back to the contract's file."""
    try:
        return os.path.basename(func.source_mapping.filename.absolute)
    except (AttributeError, TypeError):
        return "unknown"


def fn_text(func: Function) -> str:
    """The function's Solidity source text (best-effort)."""
    try:
        c = func.source_mapping.content
        if c:
            return c
    except (AttributeError, TypeError):
        pass
    return ""


_SYNTH = ("slitherConstructorVariables", "slitherConstructorConstantVariables")


def own_functions(contract: Contract):
    """Functions DECLARED in this contract (not inherited), with a real body — skips
    constructors and slither-synthetic pseudo-functions."""
    for f in getattr(contract, "functions_declared", None) or contract.functions:
        if f.is_constructor or f.name in _SYNTH:
            continue
        if not getattr(f, "is_implemented", True):
            continue  # interface/abstract, no body
        yield f


# Vendored dependency paths. NOTE: do NOT blanket-exclude /lib/ — foundry projects often
# place their OWN sub-packages there (e.g. BOB's lib/zkbob-contracts). Exclude only KNOWN
# third-party packages inside lib/.
_VENDORED_PATH = (
    "/node_modules/", "/vendor/", "/external/", "/.deps/",
    "/lib/openzeppelin", "/lib/@openzeppelin", "/lib/forge-std", "/lib/ds-test",
    "/lib/solmate", "/lib/solady", "/lib/prb-math", "/lib/prb/", "/lib/chainlink",
    "/lib/uniswap", "/lib/@uniswap", "/lib/@quickswap", "/lib/permit2", "/lib/create3",
    "/lib/openzeppelin-contracts", "/lib/forge-std/",
    # test / mock directories — deliberately-broken plugins (BadCollateralPlugin) and test doubles
    # (RejectNative) live here; they are NOT product code and only cause spurious flags.
    "/test/", "/tests/", "/mock/", "/mocks/",
)
_VENDORED_NAME = {"ERC4626", "ERC20", "ERC20Upgradeable", "ERC20Permit", "SafeERC20",
                  "Ownable", "Initializable", "ReentrancyGuard", "Address", "Math",
                  "AccessControl", "Context", "Pausable"}
_NONCORE_HINT = ("mock", "test", "example", "harness", "fixture", "scenario")


def in_scope(contract: Contract) -> bool:
    """Keep only first-party, concrete stablecoin contracts — drop interfaces, libraries
    of generic utility, vendored deps, and mocks/tests (mirrors StructuralFilter intent)."""
    if getattr(contract, "is_interface", False):
        return False
    if contract.name in _VENDORED_NAME:
        return False
    nl = contract.name.lower()
    if any(h in nl for h in _NONCORE_HINT):
        return False
    try:
        path = contract.source_mapping.filename.absolute.lower()
        if any(v in path for v in _VENDORED_PATH):
            return False
        # Foundry test files (Foo.t.sol) and *.test.sol are test code, never product.
        if path.endswith(".t.sol") or path.endswith(".test.sol"):
            return False
    except (AttributeError, TypeError):
        pass
    return True


def contract_text(contract: Contract) -> str:
    try:
        return contract.source_mapping.content or ""
    except (AttributeError, TypeError):
        return ""


# detector registry --------------------------------------------------------
DETECTORS: List[tuple] = []   # (sub, fn)


def detector(sub: str):
    def wrap(fn: Callable[[Contract], List[Candidate]]):
        DETECTORS.append((sub, fn))
        return fn
    return wrap


def _mk(sub, contract, func, reason, conf="low") -> Candidate:
    return Candidate(sub=sub, contract=contract.name, file=fn_file(func),
                     function=func.name, line=fn_line(func), reason=reason, confidence=conf)


# ===========================================================================
# C1  Backing Mis-Valuation
# ===========================================================================
@detector("S01")
def s01_self_referential_valuation(contract: Contract) -> List[Candidate]:
    """A price/value fn that reads its OWN token totalSupply and a basket/reserve/range
    value (self-referential), where the freshness depends on a separate refresh()/melt()."""
    out = []
    ctext = contract_text(contract)
    has_refresh_melt = bool(re.search(r"\b(melt|refresh|drip|exchangeRateCurrent)\s*\(", ctext))
    for f in own_functions(contract):
        if not (f.view or f.pure) and f.visibility not in ("public", "external"):
            pass
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        is_pricey = ("price" in name or "value" in name or "refpertok" in name
                     or name in ("tryprice", "managetoken", "managetokens"))
        uses_supply = "totalsupply()" in t.lower()
        # 'reserve' alone over-matches AMM pool reserves (S.spot, not self-ref backing); require
        # an own-unit backing aggregate.
        uses_basket = bool(re.search(r"basket|range|backing|stocksUsers|\bequity\b", t, re.I))
        # read-only-reentrancy self-ref pricing via pool virtual price (only WITH self-supply
        # context — standalone virtual_price over-fires on every Curve collateral)
        virtual_price = bool(re.search(r"get_virtual_price|virtual_price", t, re.I)) and uses_supply
        self_ref = is_pricey and (uses_supply and uses_basket or virtual_price) and has_refresh_melt
        # a collateral refresh() whose status/price depends on a pool virtual_price or its own
        # underlyingRefPerTok (read-only-reentrancy self-referential pricing)
        coll_selfref = (name in ("refresh", "underlyingrefpertok", "refpertok")) and \
            bool(re.search(r"get_virtual_price|virtual_price", t, re.I))
        # RevenueTrader.manageToken that prices/sells while it may skip furnace.melt
        manage_skip = ("manage" in name) and bool(re.search(r"\.price\(|sellRewards|rToken", t, re.I))
        if self_ref or coll_selfref or manage_skip:
            out.append(_mk("S01", contract, f,
                           "self-referential backing valuation (own totalSupply+basket / pool "
                           "virtual_price / refPerTok) whose freshness depends on a separate "
                           "refresh()/melt()", "medium" if self_ref else "low"))
    return out


@detector("S02")
def s02_degenerate_oracle_sentinel(contract: Contract) -> List[Candidate]:
    """A price fn returns a degenerate sentinel — (0, FIX_MAX) / type(uintN).max / a huge
    constant — typically in a try/catch oracle-failure branch, that still flows downstream."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        is_pricey = "price" in name
        # degenerate-oracle-failure forms: FIX_MAX/uint-max/(0,huge) sentinel; a hardcoded
        # pegPrice (always 1 / FIX_ONE) ignoring the real feed; or a try/catch fallback price.
        has_sentinel = bool(re.search(r"FIX_MAX|type\(\s*uint\d*\s*\)\.max|0\s*,\s*FIX_MAX|"
                                      r"pegPrice\s*=\s*(FIX_ONE|1\b)|targetPerRef\s*\(\s*\)", t))
        has_trycatch = "catch" in t and "try" in t
        # CONSUMER side: a backing/auction/shortfall fn that reads .price()/.tryPrice() inside a
        # try/catch and uses it in a decision — a degenerate sentinel flows in here too.
        is_consumer = any(k in name for k in ("rebalance", "shortfall", "nexttrade", "settle",
                                              "managetokens", "recollateral", "forwardrevenue")) \
            and bool(re.search(r"\.\s*(price|tryPrice)\s*\(|rsrAsset|asset\.price|collateral.*price", t, re.I))
        if (is_pricey and has_sentinel) or is_consumer:
            why = ("price fn returns a degenerate sentinel (FIX_MAX/uint max) on oracle failure"
                   if has_sentinel else
                   "backing/auction fn consumes a try/catch oracle price that can be a degenerate "
                   "sentinel (0/FIX_MAX) without rejecting it")
            out.append(_mk("S02", contract, f, why, "medium" if has_trycatch else "low"))
    return out


@detector("S19")
def s19_unit_dimension_mismatch(contract: Contract) -> List[Candidate]:
    """A valuation fn chains oracle price x ref-rate x decimals (.mul().mul()) where a wrong
    reference asset / unit / decimals silently mis-scales backing value."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        is_pricey = "price" in name or "value" in name or "refpertok" in name
        chained_mul = len(re.findall(r"\.mul\(", t)) >= 2
        # (a) cross-unit composition with a SECOND target-unit feed
        target_unit = is_pricey and chained_mul and bool(re.search(r"targetUnitChainlinkFeed|targetUnitOracle", t))
        # (b) GMX-style index-token identity assumption
        agg = bool(re.search(r"indexToken|longToken", t)) and ("_get" in name or "price" in name)
        # (b2) a multi-oracle aggregator (OracleMulti: Chainlink+Uniswap circuits) composing
        # several sources into one price — wrong cached/combined rate mis-values backing
        multi_oracle = ("readall" in name or "read" == name) and \
            (len(re.findall(r"rates?\s*\[|_read[A-Z]\w*\s*\(|\.\s*read\s*\(", t)) >= 2
             or bool(re.search(r"circuitChainlink|circuitUniswap|_quoteChainlink|_quoteUniswap|"
                               r"ModuleChainlink|ModuleUniswap", t)))
        # (c) a refPerTok / underlying conversion that scales an external exchange-rate by a
        # token's decimals — a wrong reference asset / decimals source silently mis-scales backing.
        # Covers both a literal `.decimals()` call and a stored `*Decimals` shift (shiftl_toFix).
        dec_mismatch = ("refpertok" in name) and bool(re.search(
            r"\.\s*decimals\s*\(|[A-Za-z]+Decimals\b|shiftl_toFix|exchangeRate", t))
        if target_unit or agg or multi_oracle or dec_mismatch:
            why = ("composes a feed with a SECOND target-unit feed" if target_unit else
                   "aggregates 2+ price sources / assumes an index-token identity" if (agg or multi_oracle) else
                   "refPerTok takes decimals from a token that may be the wrong reference")
            out.append(_mk("S19", contract, f, why + " → wrong unit/reference mis-values backing", "low"))
    return out


# ===========================================================================
# C4  Liquidation & Solvency-Restoration Failure
# ===========================================================================
@detector("S15")
def s15_refresh_revert_in_loop(contract: Contract) -> List[Candidate]:
    """A refresh-style fn loops over collateral/assets calling an external method on each
    with no per-item try/catch — one revert bricks the whole peg-keeping round."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        is_refresher = name in ("refresh", "settletrade") or "rebalance" in name or "settle" in name \
            or "managetokens" in name or "trackstatus" in name
        if not is_refresher:
            continue
        guarded = "try" in t and "catch" in t
        has_loop = bool(re.search(r"\bfor\s*\(", t))
        loop_refresh = has_loop and bool(re.search(r"\.\s*(refresh|status|price)\s*\(\s*\)", t))
        # single refresh/settle that does revert-prone external work (oracle/price/trade reads)
        ext_work = bool(re.search(r"price\(|latestRoundData|chainlinkFeed|oracle|tryPrice|"
                                  r"exchangeRate|refPerTok|\.refresh\(|markStatus|settleTrade", t, re.I))
        # loop case: must be unguarded. single refresh case: a try/catch on tryPrice does NOT
        # protect against a revert from oracle-deprecation elsewhere, so flag regardless.
        if (loop_refresh and not guarded) or ext_work:
            why = ("loops refresh() over collateral with no per-item try/catch — one revert aborts "
                   "the round" if loop_refresh else
                   "refresh()/settle does revert-prone oracle/price work — a single collateral revert "
                   "can brick mint/redeem/liquidate")
            out.append(_mk("S15", contract, f, why, "medium" if loop_refresh else "low"))
    return out


# ===========================================================================
# C5  Par-Redemption Violation
# ===========================================================================
@detector("S05")
def s05_subpeg_par_issuance(contract: Contract) -> List[Candidate]:
    """issue/mint/redeem only guards against DISABLED collateral (still allows IFFY/below-peg),
    or an issuancePremium-style fn returns par (FIX_ONE) when premium is off / not saved."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        # A: issue/redeem gate that permits IFFY (only blocks DISABLED, or no SOUND requirement)
        gate_disabled_only = ("issue" in name or "mint" in name or "redeem" in name) and (
            bool(re.search(r"status\s*!=\s*\w*DISABLED|!=\s*CollateralStatus\.DISABLED", t))
            or ("basketHandler" in t and "DISABLED" in t and "SOUND" not in t))
        # B: issuancePremium-style fn returning par under a flag
        premium_par = ("issuancepremium" in name) and bool(re.search(r"return\s+FIX_ONE", t))
        # C: collateral soft-default refresh for an RToken-backed collateral (PRECISION-narrow:
        #    require the paired-RToken fullyCollateralized soft-default check, not any markStatus)
        soft_default = (name == "refresh") and len(re.findall(r"markStatus\s*\(", t)) >= 2 \
            and bool(re.search(r"fullyCollateralized|pairedBasketHandler", t))
        if gate_disabled_only or premium_par or soft_default:
            out.append(_mk("S05", contract, f,
                           "sub-peg collateral issued/redeemed at par (IFFY allowed / no SOUND gate / "
                           "issuancePremium falls back to par / soft-default mis-gated) — arbitrages backers",
                           "medium" if (gate_disabled_only or premium_par) else "low"))
    return out


@detector("S18")
def s18_redemption_par_sandwich(contract: Contract) -> List[Candidate]:
    """Full-redeem path pays par in full (requires fullyCollateralized, no pro-rata cap), or a
    melt()-driven exchange-rate step that can be sandwiched by tx ordering."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        redeem_full = ("redeem" in name) and bool(re.search(r"fullyCollateralized", t))
        # PRECISION-narrow: the melt() function itself is the rate-step source; do NOT flag
        # every function that merely calls melt() (over-fires).
        is_melt = (name == "melt")
        if redeem_full or is_melt:
            why = ("full redemption pays par with no pro-rata cap (status not SOUND-gated)"
                   if redeem_full else
                   "melt()-driven exchange-rate step — discrete rate jump sandwichable by tx ordering")
            out.append(_mk("S18", contract, f, why, "medium" if redeem_full else "low"))
    return out


# ===========================================================================
# C2  Unbacked Issuance at Mint
# ===========================================================================
@detector("S09")
def s09_mint_by_request_not_received(contract: Contract) -> List[Candidate]:
    """A mint path transfers collateral IN then mints by the declared `amount`, with no
    balanceBefore/After delta — under fee-on-transfer the shortfall is unbacked."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        transfers_in = bool(re.search(r"(safeTransferFrom|transferFrom)\s*\(", t))
        mints = bool(re.search(r"\b_?mint\s*\(", t))
        delta = bool(re.search(r"balanceBefore|balanceAfter|amountReceived|received|"
                               r"balanceOf\s*\(\s*address\s*\(\s*this", t, re.I))
        # The mint can be reached through a buy/deposit/issue entry whose NAME isn't "mint" but
        # whose body still transfers an asset in then calls mint() (e.g. DAI+ Exchange._buy mints
        # USD+ after pulling USDC) — an unchecked/raw transfer-in there leaves supply unbacked.
        # NOTE: deliberately NOT "deposit" — that catches ERC4626 share-vault deposits (shares are
        # backed 1:1 by construction), a different mechanism; only stablecoin-PURCHASE entries.
        mintish_entry = any(k in name for k in ("mint", "buy", "purchase", "subscribe", "issuestable"))
        if mintish_entry and transfers_in and mints and not delta:
            out.append(_mk("S09", contract, f,
                           "mints by the requested amount after transferFrom with no "
                           "balanceBefore/After delta — fee-on-transfer collateral leaves unbacked supply",
                           "medium"))
    return out


@detector("S10")
def s10_balanceof_issuance_cap(contract: Contract) -> List[Candidate]:
    """Issuance cap / spendable equity / exposure taken from a balanceOf snapshot,
    inflatable by a direct transfer."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        bal_reserve = bool(re.search(r"balanceOf\s*\(\s*address\s*\(\s*reserve", t)) \
            or bool(re.search(r"balanceOf\s*\(\s*reserve", t))
        bal_self_cap = bool(re.search(r"balanceOf\s*\(\s*address\s*\(\s*this", t)) and \
            bool(re.search(r"limit|cap|quota|exposure|equity", t, re.I))
        is_capish = any(k in name for k in ("equity", "limit", "cap", "quota", "exposure",
                                            "available", "reserve", "minter"))
        # savings/bridge paths that read or spend a balanceOf-/snapshot-measured reserve or
        # per-bridge exposure limit (Savings spends minterReserve; bridge limit circumventable)
        reserve_spend = (any(k in name for k in ("savings", "mintinternal", "refresh", "collect",
                                                 "interest", "accrue")) and
                         bool(re.search(r"minterReserve|balanceOf\s*\(\s*address\s*\(\s*reserve|"
                                        r"\.equity\s*\(|riskExposure|reserveTarget|"
                                        r"distributeProfits|earnedInterest|calculateInterest", t))) or \
            (("mint" in name) and bool(re.search(r"\blimit\b", t)) and
             bool(re.search(r"\bminted\b", t)))
        # mint/burn quota ledger adjusted by symmetric +/- deltas (BalancedMinter: a burn
        # credits mintQuota, so the supply-vs-backing quota ledger can desync) — S10.
        quota_ledger = (("mint" in name or "burn" in name or "quota" in name) and
                        len(re.findall(r"[Qq]uota", t)) >= 2 and
                        bool(re.search(r"[Qq]uota\s*[-+]|[-+]\s*\w*[Aa]mount", t)))
        # bal_self_cap already requires balanceOf(this) AND a limit/cap/exposure/equity keyword in
        # the SAME function — that signature is specific enough to flag on its own (any function
        # name), e.g. a bridge `_mint` gating on `eur.balanceOf(address(this)) <= limit`.
        if (bal_reserve and (is_capish or bal_reserve)) or bal_self_cap or reserve_spend or quota_ledger:
            out.append(_mk("S10", contract, f,
                           "issuance cap / equity / exposure read from a balanceOf snapshot — "
                           "inflatable by a direct transfer to bypass the cap", "medium"))
    return out


@detector("S13")
def s13_authorization_gap_mint(contract: Contract) -> List[Candidate]:
    """Mint gate trusts positions[msg.sender] / a re-initializable position / a *_withCaller
    forwarder — attacker satisfies it and mints with no real collateral."""
    out = []
    # contract-level: does a privileged role control the mint CAP itself? If the only backing
    # discipline is a capacity that a `cap`/`setCap` setter can raise, a minter+capper collusion
    # mints past any real backing (GYEN Token_v1: mint is onlyMinter notMoreThanCapacity, cap() is
    # a separate onlyCapper setter).
    has_cap_setter = any(
        (fn.name.lower() in ("cap", "setcap", "setcapacity", "updatecap", "setmintcap")
         or ("cap" in fn.name.lower() and bool(re.search(r"only(Capper|Owner|Admin|Role|Governor)",
                                                         fn_text(fn) or ""))))
        for fn in own_functions(contract))
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        trusts_positions = bool(re.search(r"isMinter\s*\(\s*positions\[|positions\[\s*msg\.sender", t))
        # S13 is MINT-unbacked auth: only a MINT-context *_withCaller (mint forwarder), NOT a
        # transfer_withCaller (that is transfer impersonation, a different sub-type).
        mint_ctx = ("mint" in name) or bool(re.search(r"\b_?mint\s*\(", t))
        with_caller = ("withcaller" in name or bool(re.search(r"_withCaller", t))) and mint_ctx
        reinit = (name == "initialize" or name == "initializer") and \
            not bool(re.search(r"\binitializer\b|_disableInitializers|initialized", t))
        # position-authority gate: open/clone/challenge a position that feeds the mint gate —
        # a missing registration check here lets a forged position mint (DEURO MintingHub).
        position_gate = any(k in name for k in ("openposition", "launchchallenge", "clonposition",
                                                "clone", "registerposition")) \
            and bool(re.search(r"position|Position", t))
        # mint gated only by a privileged-mutable capacity (collusion-mintable)
        capped_mint = mint_ctx and has_cap_setter and ("mint" in name) and bool(re.search(
            r"notMoreThanCapacity|[Cc]apacity|<=\s*cap\b|\bcap\b", t))
        if trusts_positions or with_caller or reinit or position_gate or capped_mint:
            why = ("mint authority trusts positions[msg.sender]" if trusts_positions else
                   "mint *_withCaller forwards an arbitrary caller into mint auth" if with_caller else
                   "initialize() lacks an initializer/one-time guard — re-initializable" if reinit else
                   "mint is gated only by a capacity a privileged setter can raise — minter+capper "
                   "collusion mints past real backing" if capped_mint else
                   "opens/challenges a position feeding the mint gate; a missing registration check "
                   "lets a forged position mint")
            out.append(_mk("S13", contract, f, why + " → unbacked/unauthorized mint", "medium"))
    return out


@detector("S16")
def s16_liquidation_reentrancy_mint(contract: Contract) -> List[Candidate]:
    """Liquidation/challenge settlement sends native/collateral with a callback to the
    bidder before state is committed — reentrancy can mint unbacked/mispriced units."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        ctx = any(k in name for k in ("challenge", "liquidat", "finish", "settle", "bid", "absorb",
                                       "notifychallenge", "withdrawcollateral")) \
            and "avert" not in name  # avert just repays+returns collateral, not a settlement reentrancy
        # the real reentrancy point is a native/collateral PUSH to a party before state commit:
        # a low-level call{value:}, transferChallengedCollateral, or a _sendCollateral / raw
        # IERC20(collateral).transfer (a reentrant collateral token re-enters on receive).
        callback = bool(re.search(r"\.call\s*\{\s*value\s*:|transferChallengedCollateral|"
                                  r"_sendCollateral|IERC20\s*\(\s*collateral\s*\)\s*\.\s*transfer", t))
        if ctx and callback:
            out.append(_mk("S16", contract, f,
                           "liquidation/challenge settlement does an external native/collateral "
                           "transfer (callback) to the bidder before state is finalized — reentrancy", "medium"))
    return out


@detector("S17")
def s17_flashmint_burn_leg(contract: Contract) -> List[Candidate]:
    """Single-tx mint→burn roll with no cross-tx held==0 assertion — if the burn leg fails
    the minted units stay unbacked."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        mints = bool(re.search(r"\.\s*mint\s*\(|\b_?mint\s*\(", t))
        burns = bool(re.search(r"\.\s*burn\w*\s*\(|\b_?burn\w*\s*\(", t))
        rollish = any(k in name for k in ("roll", "flash", "leverage", "loop", "migrate"))
        if mints and burns and rollish:
            out.append(_mk("S17", contract, f,
                           "single-tx mint→burn roll with no held==0 invariant — a failed/skipped "
                           "burn leg leaves unbacked supply", "low"))
    return out


# ===========================================================================
# C3  Supply-Backing Ledger Desync
# ===========================================================================
@detector("S08")
def s08_coverage_ledger_desync(contract: Contract) -> List[Candidate]:
    """A burn (or mint) path that updates token supply but skips the coverage/stocks ledger
    that a sibling path updates → phantom backing."""
    out = []
    LEDGER = r"updateStocksUsers|updateStocks|stocksUsers|coverageRatio|_updateBacking|updateCoverage"
    # only meaningful if THIS contract maintains such a coverage/stocks ledger somewhere
    if not re.search(LEDGER, contract_text(contract), re.I):
        return out
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        burns = bool(re.search(r"\b_?burn\s*\(", t)) and "burn" in name
        # S08 is about FUNGIBLE supply↔backing desync; exclude ERC721 burns (tokenId/ownership)
        is_nft_burn = bool(re.search(r"tokenId|perpetualID|ownerOf|_owners\b|ERC721", t))
        updates_ledger = bool(re.search(LEDGER, t, re.I))
        if burns and not updates_ledger and not is_nft_burn:
            out.append(_mk("S08", contract, f,
                           "burn path updates supply but skips the coverage/stocks ledger a sibling "
                           "in this contract maintains → phantom backing", "medium"))
    return out


@detector("S11")
def s11_external_balance_backing(contract: Contract) -> List[Candidate]:
    """Backing / totalAssets read from a raw balanceOf (minus an estimate), inflatable by a
    direct transfer and blind to off-chain burns/yield."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        is_backing = any(k in name for k in ("totalassets", "totalbacking", "backing",
                                             "reserves", "totalreserve", "accruedyield", "getaccrued",
                                             "reward", "getreserves", "estimatedtotalassets",
                                             "forwardrevenue")) \
            and not name.endswith("balance") and "tokenbalance" not in name
        # backing/yield read from a live source not reconciled to issued supply: balanceOf, or a
        # strategy/oracle-derived asset total, or an unvested-subtracted figure.
        uses_bal = bool(re.search(r"balanceOf\s*\(|getUnvested|estimatedTotalAssets|"
                                  r"totalAssets\s*\(|underlying|strategy", t, re.I))
        if is_backing and uses_bal:
            out.append(_mk("S11", contract, f,
                           "backing/totalAssets read from raw balanceOf (±estimate) — inflatable by "
                           "direct transfer, blind to off-chain burns/yield", "medium"))
    return out


@detector("S12")
def s12_collateral_behavior_drift(contract: Contract) -> List[Candidate]:
    """Collateral recorded at transfer-in then trusted forever; raw (non-SafeERC20) transfers
    and fee/rebase/upgradeable tokens make the recorded amount drift from the real balance."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        coll_ctx = bool(re.search(r"collateral|addColl|coll\b", t, re.I)) or \
            any(k in name for k in ("addcoll", "adjust", "deposit", "openposition", "challenge"))
        raw_transfer = bool(re.search(r"(?<!safe)(?<!Safe)\b\w*\.transfer(From)?\s*\(", t)) and \
            not bool(re.search(r"safeTransfer", t))
        # BentoBox/share-vault accounting reconciles collateral internally — not record-drift
        bentobox = bool(re.search(r"bentoBox|bentobox|toShare|toAmount|\.share", t, re.I))
        if coll_ctx and raw_transfer and not bentobox:
            out.append(_mk("S12", contract, f,
                           "collateral moved via raw transfer/transferFrom (no SafeERC20) and recorded "
                           "by request amount — fee/rebase/upgradeable token drifts record≠balance", "low"))
    return out


# ===========================================================================
# C4  Liquidation & Solvency-Restoration Failure
# ===========================================================================
@detector("S03")
def s03_baddebt_not_burned(contract: Contract) -> List[Candidate]:
    """A liquidation/sale path that sells collateral and handles principal+interest but may
    leave residual bad debt without burning it against equity (coverLoss)."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        ctx = any(k in name for k in ("forcesale", "liquidat", "sale", "absorb", "settle", "recover"))
        debt_terms = bool(re.search(r"principal|interest|proceeds|badDebt|coverLoss|shortfall", t, re.I))
        if ctx and debt_terms:
            out.append(_mk("S03", contract, f,
                           "liquidation/sale handles principal+interest; residual bad debt may not be "
                           "burned against equity (coverLoss) → unbacked supply persists", "low"))
    return out


@detector("S04")
def s04_mint_to_cover_loss(contract: Contract) -> List[Candidate]:
    """Reserve shortfall covered by minting fresh stablecoin (supply up, backing flat) —
    inflationary insolvency cascade."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        reserve_ctx = bool(re.search(r"reserveLeft|reserve|cover|withdrawFromReserve|shortfall", t, re.I))
        mints = bool(re.search(r"\b_?mint\s*\(", t))
        shortfall_branch = bool(re.search(r"amount\s*-\s*reserve|reserveLeft|else\s*\{[^}]*_?mint", t, re.I))
        # liquidation-settlement that mints/covers a loss (interest-not-separated / bad-debt)
        liq_mint = any(k in name for k in ("finishchallenge", "forcesale", "absorb", "settle")) and \
            bool(re.search(r"\b_?mint\s*\(|\.mint\s*\(|coverLoss|withdrawFromReserve|_withdrawFromReserve", t))
        if (reserve_ctx and mints and shortfall_branch) or liq_mint:
            out.append(_mk("S04", contract, f,
                           "reserve shortfall covered by _mint (supply↑, backing flat) — inflationary "
                           "insolvency cascade", "medium"))
    return out


@detector("S06")
def s06_liquidation_evasion(contract: Contract) -> List[Candidate]:
    """A challenged/undercollateralized position that may not close (challenge never zeroes /
    avertable / collateral pulled) while minting can continue."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        ctx = any(k in name for k in ("challenge", "notifychallenge", "close", "bid",
                                      "expired", "avert", "splitchallenge"))
        terms = bool(re.search(r"challengedAmount|_close|_restrictMinting|avert|expired|"
                               r"buyExpiredCollateral", t, re.I))
        # *Allowed / *allowed are view permission PREDICATES (return a bool), not the execution
        # path where liquidation-evasion lives — skip them (e.g. ActionUtils.buyExpiredCollateralAllowed).
        if name.endswith("allowed"):
            continue
        if ctx and terms:
            out.append(_mk("S06", contract, f,
                           "challenge/close path keyed on challengedAmount / avertable / expired — "
                           "position may stay open and keep minting unbacked", "low"))
    return out


@detector("S14")
def s14_privileged_oracle_reroute(contract: Contract) -> List[Candidate]:
    """A privileged setter swaps the oracle/component that defines the redemption/conversion
    price; after the swap a legitimate redemption pays out at a forged par value."""
    out = []
    for f in own_functions(contract):
        t = fn_text(f)
        if not t:
            continue
        name = f.name.lower()
        # "set" must be a real setter, not the substring inside unset/reset/remove — UNsetting an
        # oracle removes it (the call reverts on read), it does not reroute price to a forged par.
        sets_oracle = (("oracle" in name and "set" in name and "unset" not in name
                        and "reset" not in name and "remove" not in name)
                       or bool(re.search(r"\.\s*oracle\s*=|col\.oracle\s*=|setOracle", t))) \
            and "unset" not in name and "remove" not in name
        privileged = bool(re.search(r"onlyRole|onlyOwner|onlyGovernor|GOVERNOR|onlyAdmin|onlyGuardian", t))
        if sets_oracle and privileged:
            out.append(_mk("S14", contract, f,
                           "privileged setter reroutes the oracle defining redemption/conversion price "
                           "→ redemption pays out at a forged par value", "medium"))
    return out


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def run_detectors(contracts, only: Optional[set] = None) -> List[Candidate]:
    """Run all (or a subset of) detectors over the given slither contracts."""
    out: List[Candidate] = []
    for contract in contracts:
        if not in_scope(contract):
            continue
        for sub, fn in DETECTORS:
            if only and sub not in only:
                continue
            try:
                out.extend(fn(contract))
            except Exception as e:  # one bad contract must not kill the sweep
                logger.debug(f"detector {sub} failed on {contract.name}: {e}")
    return out
