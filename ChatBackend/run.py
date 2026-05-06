from app import create_app
from datetime import datetime
import traceback

# Create app instance - might be useful for Flask CLI commands defined below
# Note: This instance is NOT directly used by Gunicorn/Celery.
# Gunicorn uses wsgi.py, Celery uses celery_app.py.
app = create_app()

# (Optional but recommended) Define Flask CLI commands here if needed
# Example: A command to manually trigger cache update
# @app.cli.command("update-cache")
# def update_cache_command():
#     """Manually updates the hot news cache."""
#     print("Manually updating hot news cache via CLI...")
#     update_hot_news_cache() # Call the existing function
#     print("Manual cache update finished.")

# Definition of the function remains, maybe useful for CLI or other parts
def update_hot_news_cache():
    """Function to update hot news cache. Can be called manually or via CLI."""
    # We need an app context to run this
    if not app:
        print("Error: Flask application instance not available for update_hot_news_cache.")
        return {"status": "error", "message": "Flask app not available"}

    print(f"[{datetime.now()}] 更新热搜新闻缓存...")
    # Import service within the function if not already imported globally
    # or ensure it's available via app context
    from app.services.news_service import NewsService
    
    try:
        with app.app_context():
            result = NewsService.update_current_hot_news()
            print(f"热搜新闻缓存更新结果: {result}")
            return result
    except Exception as e:
        print(f"更新热搜新闻缓存失败: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# For development mode, run the Flask app directly
if __name__ == '__main__':
    # Ensure the server doesn't exit immediately in development mode
    app.run(host='0.0.0.0', port=5000, debug=True)

# The original if __name__ == '__main__': block is removed.
# Running the app directly or starting the old scheduler is no longer needed.
# Gunicorn runs the web server via wsgi.py.
# Celery runs the background tasks via celeryworker and celerybeat services. 