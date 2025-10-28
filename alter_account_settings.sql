-- 1. enable cross-region inference for claude-sonnet-4-5
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- 2. Create a network policy that allows all IPs
CREATE NETWORK POLICY allow_all
    ALLOWED_IP_LIST = ('0.0.0.0/0');

-- Apply it to your account (optional — you can apply at user or account level)
ALTER ACCOUNT SET NETWORK_POLICY = allow_all;

-- 3. Grant permissions for AI Observability

USE ROLE ACCOUNTADMIN;

SET my_user = CURRENT_USER;

CREATE ROLE observability_user_role;

GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE observability_user_role;

GRANT APPLICATION ROLE SNOWFLAKE.AI_OBSERVABILITY_EVENTS_LOOKUP TO ROLE observability_user_role;

GRANT CREATE EXTERNAL AGENT ON SCHEMA PUBLIC TO ROLE observability_user_role;

GRANT CREATE TASK ON SCHEMA PUBLIC TO ROLE observability_user_role;

GRANT EXECUTE TASK ON ACCOUNT TO ROLE observability_user_role;

GRANT ROLE observability_user_role TO USER IDENTIFIER($my_user);