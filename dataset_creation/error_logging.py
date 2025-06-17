# error_logging.py
import logging
import logging.handlers
import queue

log_queue = queue.Queue()

# The handler that actually writes to the file
file_handler = logging.FileHandler("errors.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# The handler that other threads use to submit log records
queue_handler = logging.handlers.QueueHandler(log_queue)

# Shared error logger used across all threads
error_logger = logging.getLogger("shared_error_logger")
error_logger.setLevel(logging.ERROR)
error_logger.addHandler(queue_handler)

# A listener that runs in a dedicated thread to write logs from the queue
listener = logging.handlers.QueueListener(log_queue, file_handler)
listener.start()
