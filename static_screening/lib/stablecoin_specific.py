"""
Stablecoin-specific defect taxonomy (C1-C5 / S01-S19), 2026-06-24.

A PARALLEL taxonomy to `taxonomy.py` (the 40-type mechanism taxonomy stays intact).
This one is organized around the single stablecoin invariant -- *every issued unit is
genuinely backed* -- and is sourced from `STABLECOIN_DEFECT_EXTRACTION.md` + the labeled
dataset `stablecoin_specific_full.csv` (71 real audit findings across 11 projects).

Five macro classes:
  C1 Backing Mis-Valuation          -- backing valued wrong (stale self-ref / degenerate
                                        oracle sentinel / unit-dimension mismatch)
  C2 Unbacked Issuance at Mint       -- mint issues more units than backing actually received
  C3 Supply-Backing Ledger Desync    -- the "how much is backed" ledger drifts from reality
  C4 Liquidation & Solvency-Restore  -- third-party-price shortfall leaks into issued units
  C5 Par-Redemption Violation        -- the "always redeemable at par" promise is broken

`legacy_reuse` records which existing extractor(s)/DefectType(s) each sub-type leans on, and
`build` is the construction plan: reuse | extend | new. See task_plan.md "新主线".
"""
from __future__ import annotations
from dataclasses import dataclass, field


MACRO = {
    "C1": "Backing Mis-Valuation / 背书估值缺陷",
    "C2": "Unbacked Issuance at Mint / 无背书铸造缺陷",
    "C3": "Supply-Backing Ledger Desync / 供应↔背书记账缺陷",
    "C4": "Liquidation & Solvency-Restoration Failure / 清算与偿付缺陷",
    "C5": "Par-Redemption Violation / 面值赎回缺陷",
}


@dataclass(frozen=True)
class SubDefect:
    id: str            # "S01"
    macro: str         # "C1"
    name: str          # canonical English type name (from CSV 类型名)
    cn: str            # short Chinese label
    definition: str    # concise mechanism (from STABLECOIN_DEFECT_EXTRACTION.md)
    build: str         # "reuse" | "extend" | "new"
    legacy_reuse: tuple = ()   # existing extractor file stems / DefectType.value it leans on
    n_dataset: int = 0         # labeled findings in stablecoin_specific_full.csv


SUBDEFECTS = {
    # ---- C1 Backing Mis-Valuation ----
    "S01": SubDefect("S01", "C1",
        "Self-referential backing valuation corrupts the unit-of-account's own price",
        "自指背书定价(读陈旧)",
        "Prices a unit from its own internal backing state (basket value / totalSupply) and "
        "reads the book value BEFORE the required refresh()/melt(), so a stale self-referential "
        "price propagates downstream. Never reverts.",
        "new", ("vault_share_price_oracle",), 4),
    "S02": SubDefect("S02", "C1",
        "Degenerate oracle-failure price (0 / FIX_MAX) triggers fire-sale of the reserve",
        "退化喂价(0/FIX_MAX)",
        "On oracle timeout/deprecation the feed falls back to a sentinel (0, FIX_MAX) which still "
        "flows into the backing/auction path and is treated as a real price -> assets sold at 0 "
        "or accepted at an absurd high.",
        "extend", ("oracle_validation", "oracle_bound_check"), 7),
    "S19": SubDefect("S19", "C1",
        "Unit / dimension mismatch in the backing-valuation pipeline",
        "维度/单位错配",
        "The valuation pipeline multiplies components (oracle price x ref-exchange-rate x decimals) "
        "with a wrong unit semantics or a wrong reference asset, so backing value is systematically "
        "mis-computed even though every feed is fresh, non-zero, and does not revert.",
        "extend", ("oracle_decimal",), 5),

    # ---- C2 Unbacked Issuance at Mint ----
    "S09": SubDefect("S09", "C2",
        "Mint-input vs collateral-received mismatch creates unbacked stablecoin supply",
        "铸币按请求额而非实收",
        "Mints against the declared `amount` rather than the contract's actual received delta "
        "(balanceBefore/After). Under a fee-on-transfer collateral the shortfall is unbacked.",
        "extend", ("mint_guards", "fee_on_transfer"), 3),
    "S10": SubDefect("S10", "C2",
        "Issuance-cap / backing measured by balanceOf (bypassable)",
        "发行上限/背书按balanceOf(可绕过)",
        "Takes the backing / spendable equity / exposure cap from a balanceOf snapshot "
        "(equity = balanceOf(reserve) - minterReserve; bridge exposure = token.balanceOf(this)), "
        "which anyone can inflate by a direct transfer to bypass the cap.",
        "reuse", ("balanceof_accounting",), 3),
    "S13": SubDefect("S13", "C2",
        "Authorization gap mints unbacked stablecoin supply",
        "越权直达铸币权",
        "The mint gate trusts positions[msg.sender] (or a re-initializable / forged / colluding "
        "position) that an attacker can satisfy -> mint with zero real collateral.",
        "extend", ("mint_guards", "access_control_guards", "upgradeable_init"), 6),
    "S16": SubDefect("S16", "C2",
        "Reentrancy/hook during liquidation mints unbacked or mispriced stable units",
        "清算回调重入铸",
        "Settlement sends native/collateral to a bidder with a callback before state is committed; "
        "the reentrant call mints unbacked or mispriced units (ERC-721 receive hook is isomorphic).",
        "new", (), 2),
    "S17": SubDefect("S17", "C2",
        "Flash-mint / atomic mint-burn assumption leaves unbacked supply if the burn leg fails",
        "闪铸burn腿失败留无背书",
        "A single-tx mint->burn roll has no cross-tx `held==0` assertion, so if the burn leg fails "
        "(or is skipped) the minted units remain unbacked.",
        "new", (), 1),

    # ---- C3 Supply-Backing Ledger Desync ----
    "S08": SubDefect("S08", "C3",
        "Coverage-ratio / minted-supply accounting desync creates phantom backing",
        "覆盖率/已铸供应失步",
        "Some burn/mint paths skip the ledger update (e.g. stocksUsers), so the recorded coverage "
        "ratio overstates backing = phantom backing.",
        "new", (), 1),
    "S11": SubDefect("S11", "C3",
        "Supply-backing ledger desync from un-reconciled direct burns and external/stale balances",
        "直接销毁/外部余额未对账",
        "Backing is read from a raw balanceOf (minus an estimate), which a direct transfer can "
        "inflate and which does not reflect off-chain burns/yield -> ledger drifts from reality.",
        "reuse", ("balanceof_accounting",), 5),
    "S12": SubDefect("S12", "C3",
        "Collateral-token behavior drift breaks backing accounting",
        "抵押代币行为漂移",
        "Collateral is recorded at transfer-in amount then trusted forever; an upgradeable / "
        "fee-on-transfer / rebasing token drifts post-hoc so the recorded amount != real balance.",
        "extend", ("fee_on_transfer", "multi_token"), 5),

    # ---- C4 Liquidation & Solvency-Restoration Failure ----
    "S03": SubDefect("S03", "C4",
        "Bad debt from liquidation never burned against equity, leaving unbacked supply",
        "清算坏账未对权益销账",
        "After collateral is sold off, an outstanding principal+interest remains but coverLoss is "
        "not invoked, so the already-minted units stay unbacked.",
        "new", (), 3),
    "S04": SubDefect("S04", "C4",
        "Peg-stabilizing reserve mints fresh stablecoin to cover liquidation losses (inflationary)",
        "增发稳定币弥补清算亏空",
        "When the reserve is insufficient, the shortfall is covered by `_mint` -> supply up, backing "
        "flat = inflationary insolvency cascade.",
        "new", (), 4),
    "S06": SubDefect("S06", "C4",
        "Liquidation evasion/blocking leaves an undercollateralized position open to keep minting",
        "清算被规避→持续增发",
        "A position cannot be closed (challenge never zeroes / zero min-duration / collateral pulled) "
        "yet can keep minting at an inflated price limit.",
        "new", ("liquidation_extras",), 5),
    "S07": SubDefect("S07", "C4",
        "System-wide recovery-mode / global-LTV solvency trigger weaponized to liquidate healthy collateral",
        "聚合LTV/恢复模式被武器化",
        "Recovery mode is triggered by a global aggregate LTV that a flash loan can push past the "
        "threshold, liquidating healthy positions.",
        "extend", ("tcr_calculation",), 1),
    "S15": SubDefect("S15", "C4",
        "Collateral-refresh revert bricks the whole peg-keeping engine",
        "单抵押refresh-revert瘫痪",
        "A loop refreshes each collateral; a single revert aborts the whole round, freezing "
        "mint/redeem/recollateralize/liquidate.",
        "new", ("internal_call_in_loop",), 4),

    # ---- C5 Par-Redemption Violation ----
    "S05": SubDefect("S05", "C5",
        "Sub-peg collateral lets users mint/issue (or redeem) at par, arbitraging the peg against backers",
        "次锚抵押按面值铸/赎",
        "Collateral that is only IFFY / below peg is still minted/redeemed at par with no "
        "issuancePremium, so an arbitrageur extracts value from backers.",
        "new", (), 6),
    "S14": SubDefect("S14", "C5",
        "Privileged oracle/component reroute drains reserve at corrupted par value",
        "特权重定向赎回价oracle",
        "A privileged role can swap the oracle that defines the redemption/conversion price; after "
        "the swap a legitimate redemption path pays out at a forged par value.",
        "extend", ("access_control_guards", "oracle_validation"), 2),
    "S18": SubDefect("S18", "C5",
        "Redemption honeypot during undercollateralization / appreciation sandwich on the peg-price step",
        "赎回蜜罐/peg价步进三明治",
        "The full-redemption path pays par in full with no pro-rata cap when only momentarily fully "
        "collateralized; a melt-driven exchange-rate step can be sandwiched by transaction ordering.",
        "extend", ("redemption_entry",), 4),
}


# Build-plan partitions (for task_plan N3).
REUSE = tuple(s for s in SUBDEFECTS if SUBDEFECTS[s].build == "reuse")
EXTEND = tuple(s for s in SUBDEFECTS if SUBDEFECTS[s].build == "extend")
NEW = tuple(s for s in SUBDEFECTS if SUBDEFECTS[s].build == "new")


def subdefects_in_macro(macro_id: str):
    return [s for s in SUBDEFECTS.values() if s.macro == macro_id]


if __name__ == "__main__":
    total = sum(s.n_dataset for s in SUBDEFECTS.values())
    print(f"Stablecoin-specific taxonomy: {len(MACRO)} macro / {len(SUBDEFECTS)} sub-types "
          f"({total} labeled findings)\n")
    for mid, mname in MACRO.items():
        subs = subdefects_in_macro(mid)
        print(f"{mid}  {mname}  ({sum(s.n_dataset for s in subs)} findings)")
        for s in subs:
            print(f"   {s.id} [{s.build:<6}] {s.cn:<24} n={s.n_dataset}  reuse={list(s.legacy_reuse)}")
    print(f"\nbuild plan: reuse={list(REUSE)}  extend={list(EXTEND)}  new={list(NEW)}")
