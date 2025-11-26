import os
import ssl
import urllib3

from logger import get_logger
from kubernetes.config.kube_config import KUBE_CONFIG_DEFAULT_LOCATION
from kubernetes import client, config
from requests.packages.urllib3.util.retry import Retry

from helpers import REQ_RETRY_TOTAL, REQ_RETRY_CONNECT, REQ_RETRY_READ, REQ_RETRY_BACKOFF_FACTOR

# Get logger
logger = get_logger()

SKIP_TLS_VERIFY = "SKIP_TLS_VERIFY"
DISABLE_X509_STRICT_VERIFICATION = "DISABLE_X509_STRICT_VERIFICATION"


def _initialize_kubeclient_configuration():
    """
    Updates the default configuration of the kubernetes client. This is
    picked up later on automatically then.
    """

    # this is where kube_config is going to look for a config file
    kube_config = os.path.expanduser(KUBE_CONFIG_DEFAULT_LOCATION)
    try:
        if os.path.exists(kube_config):
            logger.info(f"Loading config from '{kube_config}'...")
            config.load_kube_config(kube_config)
        else:
            logger.info("Loading incluster config...")
            config.load_incluster_config()
    except ssl.SSLCertVerificationError as e:
        logger.error(f"SSL certificate verification failed when initializing Kubernetes client: {e}")
        logger.error("Check if the CA certificate at /var/run/secrets/kubernetes.io/serviceaccount/ca.crt is correct or set SKIP_TLS_VERIFY=true (insecure).")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during Kubernetes client initialization: {e}")
        raise

    if os.getenv(SKIP_TLS_VERIFY) == "true":
        configuration = client.Configuration.get_default_copy()
        configuration.verify_ssl = False
        configuration.debug = False
        client.Configuration.set_default(configuration)

    # push urllib3 retries to k8s client config
    configuration = client.Configuration.get_default_copy()
    configuration.retries = Retry(total=REQ_RETRY_TOTAL,
                                  connect=REQ_RETRY_CONNECT,
                                  read=REQ_RETRY_READ,
                                  backoff_factor=REQ_RETRY_BACKOFF_FACTOR)
    client.Configuration.set_default(configuration)

    logger.debug(f"Config for cluster api at '{configuration.host}' loaded.")

def _ensure_kube_config_in_child():
    """Ensure Kubernetes client is configured inside forked/spawned processes."""
    # Try in-cluster first (works in Pods), fall back to kubeconfig for local runs/tests.
    try:
        # Prefer in-cluster if SA token present or env is set
        if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token") or os.getenv("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config()
        else:
            config.load_kube_config()
    except Exception:
        # Last resort: try kubeconfig (useful for local test runners)
        try:
            config.load_kube_config()
        except Exception as e:
            # Don't swallow - make it visible in logs
            logger.error(f"Failed to initialize Kubernetes config in child process: {e}")
            raise

    # Mirror retry setup from main process
    configuration = client.Configuration.get_default_copy()
    configuration.retries = Retry(
        total          = REQ_RETRY_TOTAL,
        connect        = REQ_RETRY_CONNECT,
        read           = REQ_RETRY_READ,
        backoff_factor = REQ_RETRY_BACKOFF_FACTOR,
    )
    client.Configuration.set_default(configuration)
    logger.info(f"[child] Kubernetes client configured for host: {configuration.host}")

def get_api_client():
    """
    Returns a configured ApiClient.
    Handles DISABLE_X509_STRICT_VERIFICATION if set.
    """
    api_client = client.ApiClient()

    if os.getenv(DISABLE_X509_STRICT_VERIFICATION, "false").lower() == "true":
        logger.warning("Disabling strict X.509 certificate verification")
        # Relax OpenSSL TLS validation to support legacy root CA certificates
        # (e.g. from Kubernetes <= 1.16) which may not satisfy the stricter
        # VERIFY_X509_STRICT flags enforced by default in Python 3.13+.

        ctx = ssl.create_default_context()
        ctx.verify_flags = ctx.verify_flags & ~ssl.VERIFY_X509_STRICT

        # We need to recreate the pool manager with the new SSL context
        # We try to preserve existing pool manager arguments
        pool_args = api_client.rest_client.pool_manager.connection_pool_kw

        api_client.rest_client.pool_manager = urllib3.PoolManager(
            num_pools=4,
            ssl_context=ctx,
            **pool_args,
        )

    return api_client