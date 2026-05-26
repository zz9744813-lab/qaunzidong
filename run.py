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

    print("=" * 50)
    print("Novel Auto Factory started!")
    print("Access the web interface at: http://127.0.0.1:8000")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()