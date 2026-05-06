from ChatBackend.app import create_app
import logging
import os

# 配置logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
debug_raw = os.environ.get("WANXIANG_BACKEND_DEBUG") or os.environ.get("ZHIMO_BACKEND_DEBUG") or ""
debug_enabled = debug_raw.strip().lower() in {"1", "true", "yes", "on"}
logger.debug("Starting application in %s mode", "debug" if debug_enabled else "stable")

app = create_app()
 
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=debug_enabled)
