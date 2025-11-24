#!/bin/bash
# Quick launcher for the Kimi Book Writer Web UI

echo "🚀 Starting Kimi Book Writer Web UI..."
echo ""

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "   Creating from template..."
    cp .env.example .env 2>/dev/null
    echo "   Please edit .env and add your MOONSHOT_API_KEY"
    echo ""
fi

# Check if streamlit is installed
if ! python -c "import streamlit" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -e . || {
        echo "❌ Installation failed. Please install dependencies manually:"
        echo "   pip install -e ."
        exit 1
    }
    echo ""
fi

# Start Streamlit
echo "✨ Opening web UI..."
echo "   (Press Ctrl+C to stop)"
echo ""
streamlit run app.py --server.headless true
