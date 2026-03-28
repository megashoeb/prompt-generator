# Mythology Prompt Generator

Converts SRT subtitle files into Nano Banana-optimized image generation prompts for mythology YouTube channels.

## Features
- Auto-chunks SRT based on scene breaks
- Parallel API calls for speed
- Character card extraction and consistency
- Sacred Figure Protocol (Prophets never depicted)
- Shot variety tracking
- Export to .txt and .xlsx
- Works on Windows and Mac

## Installation

### Prerequisites
- Python 3.10 or higher
- OpenRouter API key (free from https://openrouter.ai)

### Windows
```
cd path\to\mythology-prompt-tool
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### Mac / Linux
```
cd path/to/mythology-prompt-tool
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Browser opens automatically at http://localhost:8501

## Usage
1. Enter API Key in sidebar
2. Upload SRT file
3. Select Mode (Image Only or Image + Video)
4. Click Generate
5. Download .txt or .xlsx

## Adding More Models
In app.py find the model selectbox and add:
```python
model = st.selectbox("Model", [
    "stepfun/step-3.5-flash:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
])
```

## Customization
Edit system_prompt.txt to change prompt rules, style, or character protocol.
