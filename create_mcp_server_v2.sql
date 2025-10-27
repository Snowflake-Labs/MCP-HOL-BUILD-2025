USE ROLE ACCOUNTADMIN;
use warehouse mcp_wh;
use database health_db;
use schema public;
create or replace mcp server health_mcp_server_v2 from specification
$$
tools:
  - name: "pubmed_search"
    identifier: "PUBMED_BIOMEDICAL_RESEARCH_CORPUS.OA_COMM.PUBMED_OA_CKE_SEARCH_SERVICE"
    type: "CORTEX_SEARCH_SERVICE_QUERY"
    description: "Search peer-reviewed medical literature from NIH/NLM PubMed. MANDATORY USE for drug indications, efficacy, safety, mechanisms, treatment comparisons, and medical facts. USAGE: Only provide 'query' parameter with search terms - service automatically searches all content."
    title: "PubMed"
  - name: "clinical_trials_search"
    identifier: "CLINICAL_TRIALS_RESEARCH_DATABASE.CT.CLINICAL_TRIALS_SEARCH_SERVICE"
    type: "CORTEX_SEARCH_SERVICE_QUERY"
    description: "Search global clinical trials database. MANDATORY USE for drug approved indications, trial recruitment, eligibility criteria, trial designs, endpoints, and regulatory pathways. USAGE: Only provide 'query' parameter with search terms - service automatically searches all trial fields."
    title: "Clinical Trials"
$$;

USE ROLE ACCOUNTADMIN;

GRANT USAGE ON MCP SERVER health_mcp_server_v2 TO ROLE PUBLIC;