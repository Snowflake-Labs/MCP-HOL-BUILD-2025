-- enable cross-region inference for claude-sonnet-4-5
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- 1. Create a network policy that allows all IPs
CREATE NETWORK POLICY allow_all
    ALLOWED_IP_LIST = ('0.0.0.0/0');

-- 2. Apply it to your account (optional — you can apply at user or account level)
ALTER ACCOUNT SET NETWORK_POLICY = allow_all;
