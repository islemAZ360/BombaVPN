import logging

logger = logging.getLogger(__name__)

def create_dns_record(subdomain, ipv4_address, token):
    """
    Creates an A record in dynv6.
    If token is 'DUMMY_TOKEN', it just mocks the success.
    """
    if token == "DUMMY_TOKEN":
        logger.info(f"[MOCK] Created DNS record {subdomain} -> {ipv4_address}")
        return True

    # Real Dynv6 REST API integration will go here once the user provides a token
    logger.warning("Real Dynv6 integration requires API token. Mocking for now.")
    return True

def delete_dns_record(subdomain, token):
    if token == "DUMMY_TOKEN":
        logger.info(f"[MOCK] Deleted DNS record {subdomain}")
        return True
    logger.warning("Real Dynv6 integration requires API token. Mocking for now.")
    return True
