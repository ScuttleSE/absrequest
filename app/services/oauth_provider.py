def register_oauth_provider(oauth, app):
    """Register the OIDC OAuth2 provider with Authlib if configured.

    Returns True if the provider was registered, False if skipped.

    Preferred: set OAUTH2_SERVER_METADATA_URL to the provider's OIDC
    discovery document (e.g. https://auth.example.com/.well-known/openid-configuration).
    Authlib will then discover all endpoints — including jwks_uri — automatically.

    Fallback: set the individual OAUTH2_AUTHORIZATION_URL / OAUTH2_TOKEN_URL /
    OAUTH2_USERINFO_URL variables.  If the provider exposes a JWKS endpoint,
    also set OAUTH2_JWKS_URI; otherwise ID-token signature validation is skipped
    and userinfo is fetched directly from OAUTH2_USERINFO_URL.
    """
    if not app.config.get('OAUTH2_CONFIGURED'):
        return False

    server_metadata_url = app.config.get('OAUTH2_SERVER_METADATA_URL', '')

    if server_metadata_url:
        # Discovery mode — Authlib fetches jwks_uri and all other endpoints
        oauth.register(
            name='oidc',
            client_id=app.config['OAUTH2_CLIENT_ID'],
            client_secret=app.config['OAUTH2_CLIENT_SECRET'],
            server_metadata_url=server_metadata_url,
            client_kwargs={'scope': app.config['OAUTH2_SCOPE']},
        )
    else:
        # Manual mode — individual endpoint URLs
        kwargs = dict(
            name='oidc',
            client_id=app.config['OAUTH2_CLIENT_ID'],
            client_secret=app.config['OAUTH2_CLIENT_SECRET'],
            authorize_url=app.config['OAUTH2_AUTHORIZATION_URL'],
            access_token_url=app.config['OAUTH2_TOKEN_URL'],
            userinfo_endpoint=app.config['OAUTH2_USERINFO_URL'],
            client_kwargs={'scope': app.config['OAUTH2_SCOPE']},
        )
        jwks_uri = app.config.get('OAUTH2_JWKS_URI', '')
        if jwks_uri:
            kwargs['jwks_uri'] = jwks_uri
        oauth.register(**kwargs)

    return True
