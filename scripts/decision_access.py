"""Verify the manager capability on the server, outside public view state."""
from hashlib import sha256
from hmac import compare_digest
import os
import time

import streamlit as st

# SHA-256 of a randomly generated 256-bit access code. The code is stored
# separately with the site owner. A new deployment can override this verifier.
OWNER_CODE_HASH = 'f739ee76bf5910b8abb39debbdd4459c5dc823a8eb041cfd05027fc4956653c0'
SESSION = 'decision_manager_session'


def verifier():
    return os.environ.get('SONARNET_MANAGER_CODE_SHA256', OWNER_CODE_HASH)


def manager_is_signed_in():
    session = st.session_state.get(SESSION)
    return bool(session and session['expires'] > time.monotonic()
                and compare_digest(session['verifier'], verifier()))


def require_manager():
    if manager_is_signed_in():
        return True
    st.session_state.pop(SESSION, None)
    with st.form('decision_manager_login', clear_on_submit=True, border=False):
        code = st.text_input('Mã truy cập quản lý', type='password', max_chars=160)
        submitted = st.form_submit_button('Mở trang quản lý', type='primary')
    if submitted:
        if compare_digest(sha256(code.strip().encode()).hexdigest(), verifier()):
            st.session_state[SESSION] = {'expires': time.monotonic() + 4 * 60 * 60,
                                         'verifier': verifier()}
            st.rerun()
        st.error('Mã truy cập quản lý không hợp lệ.')
    return False


def sign_out():
    st.session_state.pop(SESSION, None)
