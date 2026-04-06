import streamlit as st

_CSS = """
<style>
/* Pin default Streamlit chat input without changing its look */
div[data-testid="stChatInput"] {
    position: fixed;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: var(--content-width, 700px);
    max-width: 90vw;
    z-index: 1000;
    background: transparent;
}
/* Prevent messages from being hidden behind the input */
.stMainBlockContainer {
    padding-bottom: 7.5rem;
}
</style>
"""


def inject_styles():
    st.markdown(_CSS, unsafe_allow_html=True)
