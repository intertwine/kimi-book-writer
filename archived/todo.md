# TODO

## Completed: Sidebar Progress Panel (2026-01-01)

Implemented background thread-based generation with sidebar progress panel.

**Changes made to `app.py`:**
- Added `threading` and `streamlit.runtime.scriptrunner` imports for background thread support
- Added `GenStatus` type alias and `init_gen_session_state()` for generation state management
- New session state keys: `gen_status`, `gen_progress_current`, `gen_progress_total`, `gen_progress_pct`, `gen_last_chapter`, `gen_message`, `gen_title`, `gen_thread`
- Refactored `generate_novel()` and `continue_novel()` to use `_generation_worker()` in a background thread via `start_generation_thread()`
- Background worker uses `add_script_run_ctx()` to safely update session state from thread
- Added `@st.fragment(run_every=1)` sidebar progress panel (`render_sidebar_progress()`) that auto-refreshes to show live generation status
- Updated `render_generate_tab()` with proper button states (disabled "Generation Completed" / "Generation Error" buttons)
- Updated Library tab to disable "Continue" button while generation is running

**Validation:**
- UI remains responsive during generation; Library/Reader tabs accessible
- Sidebar shows live progress bar, chapter count, and status message
- Pause button sets `stop_generation=True`; worker checks this flag and sets status to "paused"
- On completion, "Generation Completed" disabled button appears with success message
- On error, "Generation Error" disabled button appears with error message
- "Clear Status" button in sidebar resets to idle state
