from __future__ import annotations

import argparse
import logging
import sys

from eval.benchmarks.swe_verified.assets import (
    load_smoke_asset_bundle,
    validate_official_dataset_alignment,
    validate_smoke_assets,
)


logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SWE-bench Verified smoke assets.")
    parser.add_argument(
        "--skip-official-dataset",
        action="store_true",
        help="Skip alignment checks against the upstream SWE-bench Verified dataset.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    bundle = load_smoke_asset_bundle()
    logger.info("Loaded smoke asset bundle for slice %s", bundle.manifest.slice_id)
    issues = validate_smoke_assets(bundle)
    if not args.skip_official_dataset:
        try:
            issues.extend(validate_official_dataset_alignment(bundle))
        except ModuleNotFoundError as exc:
            logger.error(
                "Official dataset alignment requires the optional 'datasets' dependency. "
                "Re-run with --skip-official-dataset or use an environment where 'datasets' is installed."
            )
            logger.error("Original import failure: %s", exc)
            return 2

    if issues:
        for issue in issues:
            logger.error(issue)
        return 1

    logger.info(
        "Validated SWE-bench Verified smoke assets for %s instances in slice %s.",
        len(bundle.manifest.instances),
        bundle.manifest.slice_id,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
