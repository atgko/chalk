"""Settings → More settings: the web pages Chalk links to (chalk/links.py),
so whoever keeps Chalk running after the handover can see and fix them
in one place (sponsor, Nov 9)."""

from __future__ import annotations

import streamlit as st

from chalk.errors import ChalkError
from chalk.links import LINKS_FILE, bundled_urls, load_links, overrides_path, save_links
from ui import session

_FORM = "links-form"


def render() -> None:
    st.markdown("#### Links Chalk uses")
    st.caption(
        "Every web page Chalk links to or relies on. If a page moves (for example the registrar "
        "changes the calendar's address), paste its new address here and click Save links."
    )
    links = load_links()
    with st.form(_FORM, border=False):
        urls = {}
        for link in links:
            urls[link.key] = st.text_input(
                link.label + (" (changed on this computer)" if link.is_changed else ""),
                value=link.url,
                help=link.used_for,
                key=f"link-{link.key}",
            )
            st.caption(f"[Open]({link.url}) · {link.used_for}")
        save_col, reset_col = st.columns(2)
        save = save_col.form_submit_button("Save links", type="primary")
        reset = reset_col.form_submit_button("Put every link back", disabled=not any(link.is_changed for link in links))
    if save:
        _save(urls)
    if reset:
        _save(bundled_urls(), reset=True)
    st.caption(
        f"Your changes are saved on this computer in `{overrides_path()}`. To change a link for "
        f"everyone who installs Chalk, edit `{LINKS_FILE}`."
    )


def _save(urls: dict[str, str], *, reset: bool = False) -> None:
    try:
        changed = save_links(urls)
    except ChalkError as exc:
        st.error(exc.user_message)
        return
    for key in urls:
        st.session_state.pop(f"link-{key}", None)  # show the saved values on the next run
    if reset:
        session.flash("Put every link back to Chalk's own.")
    else:
        session.flash(f"Saved. {len(changed)} link(s) differ from Chalk's own." if changed else "Saved. Every link is Chalk's own.")
    st.rerun()
