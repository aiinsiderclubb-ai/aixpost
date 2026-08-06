#!/usr/bin/env python3
"""
Run the Facebook Group Fetcher Web Dashboard
"""

import sys
import os
import logging
from pathlib import Path

# Add the current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from web_app import app, socketio
    
    if __name__ == '__main__':
        print("🚀 Starting Facebook Group Fetcher Dashboard...")
        print("📊 Features:")
        print("   • Real-time progress tracking")
        print("   • Interactive group visualization")
        print("   • Automatic job scheduling")
        print("   • Multi-format export (JSON, CSV, Excel)")
        print("   • WebSocket real-time updates")
        print()
        print("🌐 Dashboard will be available at: http://localhost:8080")
        print("📱 Mobile-friendly responsive design")
        print()
        print("Press Ctrl+C to stop the server")
        print("-" * 50)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Run the application
        socketio.run(
            app,
            host='0.0.0.0',
            port=8080,
            debug=True,
            allow_unsafe_werkzeug=True
        )
        
except ImportError as e:
    print("❌ Error importing required modules:")
    print(f"   {e}")
    print()
    print("💡 Please install the required dependencies:")
    print("   pip install -r requirements.txt")
    print()
    print("🔧 Or install manually:")
    print("   pip install flask flask-socketio pandas openpyxl")
    
except KeyboardInterrupt:
    print("\n👋 Dashboard stopped by user")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc() 