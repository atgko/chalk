"""Chalk — Streamlit entry point.

    streamlit run app.py                       # choose or create a project on launch
    streamlit run app.py -- --project <folder> # open one directly

All UI code lives in the ui package (single app, views as st.tabs() —
see DECISIONS.md); all business logic lives in chalk.
"""

from ui.shell import main

main()
