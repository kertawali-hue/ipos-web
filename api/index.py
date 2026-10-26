import sys
import os

# Menambahkan root project ke sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api_server import app

# Handler serverless untuk Vercel
app = app
