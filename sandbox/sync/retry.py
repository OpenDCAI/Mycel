import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


class RetryWithBackoff:
    """Decorator: retry on transient errors with exponential backoff."""

    TRANSIENT = (OSError, ConnectionError, TimeoutError)

    def __init__(self, max_retries: int = 3, backoff_factor: int = 2):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(self.max_retries):
                try:
                    return func(*args, **kwargs)
                except self.TRANSIENT as e:
                    if attempt == self.max_retries - 1:
                        raise
                    wait_time = self.backoff_factor**attempt
                    logger.warning("Attempt %d failed: %s. Retrying in %ds...", attempt + 1, e, wait_time)
                    time.sleep(wait_time)

        return wrapper
