
// Single owner of the editor's session token: captures it from the handoff URL,
// stores it, reads it back, and builds the header every fetch in this app uses.
//
// getJWTFromCookie/getAPIHeaders used to be copy-pasted into dynamic-dropdowns.js,
// dynamic-fields.js and quill-editor-window.js as plain global function
// declarations, so whichever script loaded last silently won and a fix applied to
// one copy would appear to work or not depending on the order in index.html.
// This file must therefore load before all of them.

function captureSessionToken() {
    // The handoff token arrives in the URL *fragment*. Browsers never transmit a
    // fragment, so it stays out of nginx's access log and out of the Referer that
    // same-origin subresource requests carry - Web and BackEnd share one host
    // behind the ingress (k8s/05-ingress.yaml), so "same-origin" is the real case.
    // ?jwt= is still read, so links minted before this change keep working, and is
    // stripped from the URL either way.
    const fromFragment = new URLSearchParams(window.location.hash.slice(1)).get('jwt');
    const query = new URLSearchParams(window.location.search);
    const jwt = fromFragment || query.get('jwt');
    if (!jwt) {
        return null;
    }

    // SameSite=Strict costs nothing here: the cookie is read by JS and replayed as
    // a bearer header, never relied on to ride along with a request. Secure only
    // over https - set on plain http the browser drops the cookie outright and
    // every API call 401s, which would break local development.
    const secure = window.location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = `jwt_token=${jwt}; path=/; max-age=86400; SameSite=Strict${secure}`;
    console.log('JWT token stored in cookie');

    // Drop the token from the address bar and from this history entry.
    query.delete('jwt');
    const search = query.toString();
    history.replaceState(null, '', window.location.pathname + (search ? `?${search}` : ''));

    return jwt;
}

// Function to get JWT from cookie
function getJWTFromCookie() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'jwt_token') {
            return value;
        }
    }
    return null;
}

// Function to get headers with JWT token for API calls
function getAPIHeaders() {
    const headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json'
    };

    const jwt = getJWTFromCookie();
    if (jwt) {
        headers['Authorization'] = `Bearer ${jwt}`;
    }

    return headers;
}

captureSessionToken();
