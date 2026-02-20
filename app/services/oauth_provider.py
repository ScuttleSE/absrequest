def register_oauth_provider(oauth, app):
    """Register the OIDC OAuth2 provider with Authlib if configured.

    Returns True if the provider was registered, False if skipped.
    """
    if not app.config.get('OAUTH2_CONFIGURED'):
        return False

    oauth.register(
        name='oidc',
        client_id=app.config['OAUTH2_CLIENT_ID'],
        client_secret=app.config['OAUTH2_CLIENT_SECRET'],
        authorize_url=app.config['OAUTH2_AUTHORIZATION_URL'],
        access_token_url=app.config['OAUTH2_TOKEN_URL'],
        userinfo_endpoint=app.config['OAUTH2_USERINFO_URL'],
        client_kwargs={'scope': app.config['OAUTH2_SCOPE']},
    )
    return True
