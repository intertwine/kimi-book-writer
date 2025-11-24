#!/bin/bash

# Startup script for Kimi Book Writer Codespace

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         📚 Welcome to Kimi Book Writer! 📚              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "🚀 Quick Start:"
echo ""
echo "   1. Create a .env file with your Moonshot API key:"
echo "      cp .env.example .env"
echo "      # Then edit .env and add your MOONSHOT_API_KEY"
echo ""
echo "   2. Start the web UI:"
echo "      streamlit run app.py"
echo ""
echo "   3. Or use the CLI:"
echo "      python kimi_writer.py --help"
echo ""
echo "📖 The UI will be available at the forwarded port 8501"
echo "   (click the notification or check the Ports tab)"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp .env.example .env 2>/dev/null || echo "Note: .env.example not found"
    echo "📝 Please edit .env and add your MOONSHOT_API_KEY"
    echo ""
fi

# Optionally auto-start Streamlit (commented out by default)
# Uncomment the line below to auto-start the UI when the Codespace opens
# streamlit run app.py --server.headless true --server.port 8501 &
