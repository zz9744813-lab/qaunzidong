import os
import uvicorn
from app.main import app
from app.database import init_db

def main():
    # Create data directories
    os.makedirs("data/exports", exist_ok=True)
    os.makedirs("data/logs", exist_ok=True)

    # Initialize database
    init_db()

    print("Starting Novel Auto Factory...")
    print("Access the web interface at http://127.0.0.1:8000")

    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()