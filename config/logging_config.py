import logging, os
ROOT = os.getcwd()
LOG_FOLDER = os.path.join(ROOT, 'data', 'logs')
os.makedirs(LOG_FOLDER, exist_ok=True)
LOG_PATH = os.path.join(LOG_FOLDER, 'app.log')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s',
                    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])
logger = logging.getLogger('form15cb_demo')
