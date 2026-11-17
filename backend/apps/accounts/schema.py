from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class TenantJWTScheme(SimpleJWTScheme):
    target_class = "apps.accounts.authentication.TenantJWTAuthentication"
    name = "jwtAuth"
    priority = 1
