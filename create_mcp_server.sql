create database if not exists health_db;
use database health_db;
use schema public;
create or replace mcp server health_mcp_server from specification
$$
tools:
  - name: "pubmed_search"
    identifier: "PUBMED_BIOMEDICAL_RESEARCH_CORPUS.OA_COMM.PUBMED_OA_CKE_SEARCH_SERVICE"
    type: "CORTEX_SEARCH_SERVICE_QUERY"
    description: "A tool that performs keyword and vector search over free full-text archive of biomedical and life sciences journal articles in the U.S. National Institutes of Health's National Library of Medicine (NIH/NLM)."
    title: "PubMed"
  - name: "clinical_trials_search"
    identifier: "CLINICAL_TRIALS_RESEARCH_DATABASE.CT.CLINICAL_TRIALS_SEARCH_SERVICE"
    type: "CORTEX_SEARCH_SERVICE_QUERY"
    description: "A tool that performs keyword and vector search over clinicial trials data to retrieve relevant clinical trial data to support strategic decisions across the drug development lifecycle, from early-stage research and protocol design to regulatory submissions and market access strategies. Gain insights into trial success patterns, endpoint selection, patient population targeting, and regulatory pathways that can inform development timelines, resource allocation, and go-to-market strategies."
    title: "Clinical Trials"
$$;

USE ROLE ACCOUNTADMIN;

GRANT USAGE ON MCP SERVER health_mcp_server TO ROLE PUBLIC;