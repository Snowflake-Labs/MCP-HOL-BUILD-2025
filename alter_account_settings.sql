-- enable cross-region inference for claude-sonnet-4-5
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- 1. Create a network policy that allows all IPs
CREATE NETWORK POLICY allow_all
    ALLOWED_IP_LIST = ('0.0.0.0/0');

-- 2. Apply it to your account (optional — you can apply at user or account level)
ALTER ACCOUNT SET NETWORK_POLICY = allow_all;

-- 3. Grant permissions for TruLens to create objects in schemas
-- First, check your current role by running: SELECT CURRENT_ROLE();
-- Then replace 'YOUR_ROLE' below with that role name

USE DATABASE health_db;

-- Grant permissions to PUBLIC (if you're using that role)
GRANT ALL PRIVILEGES ON SCHEMA mcp TO ROLE PUBLIC;
GRANT ALL PRIVILEGES ON SCHEMA public TO ROLE PUBLIC;
GRANT USAGE ON DATABASE health_db TO ROLE PUBLIC;
GRANT CREATE SCHEMA ON DATABASE health_db TO ROLE PUBLIC;

-- If you're using a different role, uncomment and modify these lines:
-- GRANT ALL PRIVILEGES ON SCHEMA mcp TO ROLE <YOUR_ROLE>;
-- GRANT ALL PRIVILEGES ON SCHEMA public TO ROLE <YOUR_ROLE>;
-- GRANT USAGE ON DATABASE health_db TO ROLE <YOUR_ROLE>;
-- GRANT CREATE SCHEMA ON DATABASE health_db TO ROLE <YOUR_ROLE>;
