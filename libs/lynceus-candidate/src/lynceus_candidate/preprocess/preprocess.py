# libs/lynceus-candidate/src/lynceus_candidates/preprocess/preprocess.py

import logging
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def preprocess():
    logging.info("preprocessing")
