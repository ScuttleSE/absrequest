from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app

app = create_app()

# Trust one proxy layer for X-Forwarded-Proto / X-Forwarded-Host so that
# url_for(..., _external=True) generates https:// URLs when behind a reverse
# proxy (Nginx, Traefik, Caddy, etc.).
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

if __name__ == '__main__':
    app.run(debug=False)
