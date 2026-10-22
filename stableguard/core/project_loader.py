"""
Project loader that wraps Slither to support Foundry, Hardhat, and single-file projects.
"""
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum
from loguru import logger
from slither import Slither
from slither.core.declarations import Contract


class ProjectType(Enum):
    FOUNDRY = "foundry"
    HARDHAT = "hardhat"
    SINGLE_FILE = "single_file"
    DIRECTORY = "directory"  # Plain directory of .sol files
    UNKNOWN = "unknown"


class ProjectLoader:
    """
    Loads a Solidity project via Slither.
    Auto-detects project type and configures Slither accordingly.
    """

    def __init__(self, project_path: str, solc_version: Optional[str] = None):
        """
        Args:
            project_path: Path to project root or single .sol file
            solc_version: Optional solc version to use (e.g., "0.8.20")
        """
        self.project_path = Path(project_path).resolve()
        self.solc_version = solc_version
        self.project_type: ProjectType = ProjectType.UNKNOWN
        self.slither: Optional[Slither] = None
        self.contracts: List[Contract] = []

        if not self.project_path.exists():
            raise FileNotFoundError(f"Project path not found: {self.project_path}")

    def detect_project_type(self) -> ProjectType:
        """Detect the type of project based on file structure."""
        if self.project_path.is_file():
            if self.project_path.suffix == ".sol":
                self.project_type = ProjectType.SINGLE_FILE
            else:
                self.project_type = ProjectType.UNKNOWN
            return self.project_type

        # It's a directory
        if (self.project_path / "foundry.toml").exists():
            self.project_type = ProjectType.FOUNDRY
        elif (
            (self.project_path / "hardhat.config.js").exists()
            or (self.project_path / "hardhat.config.ts").exists()
        ):
            self.project_type = ProjectType.HARDHAT
        elif self._has_sol_files(self.project_path):
            self.project_type = ProjectType.DIRECTORY
        else:
            self.project_type = ProjectType.UNKNOWN

        return self.project_type

    @staticmethod
    def _has_sol_files(directory: Path) -> bool:
        """Check if directory contains any .sol files (recursively)."""
        return any(directory.rglob("*.sol"))

    def load_with_fallback(self, remaps=None) -> Slither:
        """
        Robust loader for directory/hardhat projects that fail normal build.
        Tries each top-level / contracts/ / src/ .sol as single-file entry,
        accumulates all contracts that parse. Raises if nothing parses.
        Does NOT replace load(); foundry should still use load().
        """
        remaps = remaps or []
        oz = self.project_path / "node_modules" / "@openzeppelin"
        if oz.exists() and not any("openzeppelin" in r.lower() for r in remaps):
            remaps = remaps + [f"@openzeppelin={oz}"]

        candidates = []
        for pat in ["*.sol", "contracts/*.sol", "src/*.sol",
                    "contracts/**/*.sol", "src/**/*.sol",
                    "packages/**/*.sol", "**/*.sol"]:
            candidates.extend(self.project_path.glob(pat))
        seen, entries = set(), []
        for c in candidates:
            cs = str(c)
            if cs in seen:
                continue
            seen.add(cs)
            low = cs.lower()
            if any(x in low for x in ["node_modules", "/test/", "/mock",
                                       ".t.sol", "/script/", "/interfaces/"]):
                continue
            entries.append(c)

        all_contracts, n_ok, errors = {}, 0, []
        for entry in entries:
            try:
                args = {}
                if remaps:
                    args["solc_remaps"] = remaps
                sl = Slither(str(entry), **args)
                for c in sl.contracts:
                    all_contracts[c.name] = c
                n_ok += 1
                self.slither = sl
            except Exception as e:
                errors.append(f"{entry.name}: {str(e)[:60]}")
                continue

        if not all_contracts:
            raise RuntimeError(
                f"fallback parsed 0 contracts from {len(entries)} entries; "
                f"sample: {errors[:3]}"
            )
        self.contracts = list(all_contracts.values())
        logger.info(f"Fallback: {len(self.contracts)} contracts from "
                    f"{n_ok}/{len(entries)} entries")
        return self.slither

    def load(self) -> Slither:
        """
        Load the project via Slither.
        Returns the Slither instance.
        """
        ptype = self.detect_project_type()
        logger.info(f"Detected project type: {ptype.value}")
        logger.info(f"Loading project from: {self.project_path}")

        slither_args: Dict[str, Any] = {}
        if self.solc_version:
            slither_args["solc_force_legacy_json"] = False

        # Use pre-built artifacts instead of recompiling, for projects whose toolchain
        # crytic can't re-drive (e.g. EURA: hardhat compiles manually but crytic's re-run
        # fails to download solc). Set SG_IGNORE_COMPILE="1"/"all" or a comma-list of project
        # basenames; the project must already have build artifacts on disk.
        import os as _os
        _ic = (_os.getenv("SG_IGNORE_COMPILE", "") or "").strip()
        if _ic and (_ic in ("1", "all") or self.project_path.name in
                    {p.strip() for p in _ic.split(",")}):
            slither_args["ignore_compile"] = True

        target: str = str(self.project_path)

        try:
            if ptype == ProjectType.FOUNDRY:
                # Slither auto-detects Foundry; we pass project root
                self.slither = Slither(target, **slither_args)
            elif ptype == ProjectType.HARDHAT:
                # Slither auto-detects Hardhat
                self.slither = Slither(target, **slither_args)
            elif ptype == ProjectType.SINGLE_FILE:
                self.slither = Slither(target, **slither_args)
            elif ptype == ProjectType.DIRECTORY:
                # Treat as plain directory; Slither will try crytic-compile defaults
                self.slither = Slither(target, **slither_args)
            else:
                raise ValueError(f"Unsupported project type: {ptype}")

            self.contracts = list(self.slither.contracts)
            logger.info(f"Loaded {len(self.contracts)} contracts")
            return self.slither

        except Exception as e:
            logger.error(f"Failed to load project: {e}")
            raise

    def get_contracts_summary(self) -> List[Dict[str, Any]]:
        """
        Return a list of summaries for all loaded contracts.
        Useful for inspection and filtering.
        """
        if not self.contracts:
            return []

        summaries = []
        for c in self.contracts:
            summary = {
                "name": c.name,
                "is_interface": c.is_interface,
                "is_library": c.is_library,
                "is_abstract": c.is_abstract,
                "kind": self._get_contract_kind(c),
                "source_file": self._get_source_file(c),
                "n_functions": len(c.functions),
                "n_state_vars": len(c.state_variables),
                "inheritance": [parent.name for parent in c.inheritance],
            }
            summaries.append(summary)
        return summaries

    @staticmethod
    def _get_contract_kind(contract: Contract) -> str:
        """Return a string describing the contract kind."""
        if contract.is_interface:
            return "interface"
        if contract.is_library:
            return "library"
        if contract.is_abstract:
            return "abstract"
        return "contract"

    @staticmethod
    def _get_source_file(contract: Contract) -> str:
        """Get the source file path for a contract."""
        try:
            return contract.source_mapping.filename.absolute
        except (AttributeError, TypeError):
            return "unknown"

    def print_summary(self):
        """Print a human-readable summary of loaded project."""
        print(f"\n{'='*70}")
        print(f"Project: {self.project_path}")
        print(f"Type: {self.project_type.value}")
        print(f"Total contracts: {len(self.contracts)}")
        print(f"{'='*70}")

        summaries = self.get_contracts_summary()
        # Group by kind
        by_kind: Dict[str, List[Dict]] = {}
        for s in summaries:
            by_kind.setdefault(s["kind"], []).append(s)

        for kind, items in sorted(by_kind.items()):
            print(f"\n[{kind}] ({len(items)})")
            for item in items:
                print(f"  - {item['name']:<40} "
                      f"funcs={item['n_functions']:<3} "
                      f"vars={item['n_state_vars']:<3} "
                      f"({Path(item['source_file']).name})")