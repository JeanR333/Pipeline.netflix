"""
Punto de entrada del pipeline (arquitectura medallón).

Uso:
    python main.py                 # ejecuta extracción + transformación
    python main.py --stage extract # solo bronze
    python main.py --stage transform # solo silver (requiere bronze)
"""

import argparse
import sys
import time

from src.extract.extract_excel import run_extract
from src.transform.clean_excel import run_transform
from src.utils import get_logger, load_config

logger = get_logger()

STAGES = {
    "extract": ("EXTRACCIÓN -> BRONZE", run_extract),
    "transform": ("TRANSFORMACIÓN -> SILVER", run_transform),
}


def main(stage: str = "all") -> int:
    config = load_config()
    to_run = list(STAGES) if stage == "all" else [stage]

    logger.info("=" * 70)
    logger.info("INICIO DEL PIPELINE '%s' | etapas: %s", config["project"]["name"], to_run)
    logger.info("=" * 70)
    t0 = time.perf_counter()

    for key in to_run:
        title, func = STAGES[key]
        logger.info("---- %s ----", title)
        t = time.perf_counter()
        try:
            func(config)
        except Exception:
            logger.exception("Falló la etapa '%s'. Pipeline detenido.", key)
            return 1
        logger.info("Etapa '%s' completada en %.2f s", key, time.perf_counter() - t)

    logger.info("PIPELINE FINALIZADO OK en %.2f s", time.perf_counter() - t0)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline medallón: bronze y silver")
    parser.add_argument("--stage", choices=["all", *STAGES], default="all")
    args = parser.parse_args()
    sys.exit(main(args.stage))
