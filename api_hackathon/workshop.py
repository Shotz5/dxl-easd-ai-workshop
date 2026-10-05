"""Participant file -- improve these working-but-unreliable baselines.

Quick start
-----------
1. Run  python demo.py          to see the raw AI output for all four levels.
2. Edit the functions below one at a time.
3. Run  python score.py --team "Your Team" --open   to see your score and a
   visual report in the browser.

The API being reviewed has three endpoints (see http://localhost:8081/api/v1):

    GET  /orders               list orders, optional ?limit=<int>
    POST /orders               create an order  (Bearer auth required)
    GET  /orders/{orderId}     fetch one order  (Bearer auth required)

The AI assistant (ai.ask(...)) always returns a list of dicts. The shapes are
shown in the comments below. Your job is to filter that list so only items
that are verifiable against real evidence survive.
"""


def review_contract(spec: dict, ai) -> list[dict]:
    findings = ai.ask("contract_review", spec)
    
    # Add this verification loop:
    verified = []
    for finding in findings:
        path = finding["path"]
        method = finding["method"]
        
        # Step 1: Does the endpoint exist?
        if path in spec["paths"] and method in spec["paths"][path]:
            verified.append(finding)
    
    return verified

def design_negative_tests(spec: dict, ai) -> list[dict]:
    """Level 2 -- return runnable test ideas for operations that really exist."""
    
    cases = ai.ask("negative_tests", spec)
    valid_statuses = {400, 401, 403, 404, 409, 422}
    filtered = []
    
    for case in cases:
        # Check 1: All required fields present
        if not all(k in case for k in ["name", "method", "path", "input", "expected_status"]):
            continue
        
        # Check 2: Expected status is valid
        if case["expected_status"] not in valid_statuses:
            continue
        
        # Check 3: Path and method exist in spec
        path = case["path"]
        method = case["method"].lower()
        
        if path not in spec.get("paths", {}):
            continue
        if method not in spec["paths"][path]:
            continue
        
        filtered.append(case)
    
    return filtered


def diagnose_incident(logs: str, ai) -> dict:
    """Level 3 -- select a diagnosis whose evidence appears in the logs.

    ai.ask("incident_diagnosis", logs) returns a list of candidates:
        [
          {
            "cause": "A DNS outage prevented all clients from reaching the API.",
            "evidence": ["dns_resolution_failed", "upstream_host_not_found"]
          },
          {
            "cause": "The 2.4.1 database-pool change exhausted connections.",
            "evidence": [
              "deploy version=2.4.1 change=orders-db-pool",
              "db_pool_wait_ms=1850 active=20 max=20",
              "status=503 error=db_pool_timeout"
            ]
          }
        ]

    Tip: only keep a candidate if every string in its "evidence" list
    appears literally somewhere inside the logs string.
    The log file is at  data/incident.log  -- open it to see what is there.
    """
    candidates = ai.ask("incident_diagnosis", logs)

    # Verify each candidate
    for candidate in candidates:
        if all(evidence in logs for evidence in candidate["evidence"]):
            return candidate
    
    # If no candidate fully verified, handle gracefully
    return None  # or raise an exception


def review_migration(v1: dict, v2: dict, ai) -> list[dict]:
    """Level 4 -- return only breaking changes proven by the two contracts."""
    findings = ai.ask("migration_review", {"v1": v1, "v2": v2})
    verified = []
    
    for finding in findings:
        path = finding["path"]
        method = finding["method"].lower()
        kind = finding["kind"]
        
        # Check if endpoint exists in the specs
        v1_op = v1.get("paths", {}).get(path, {}).get(method)
        v2_op = v2.get("paths", {}).get(path, {}).get(method)
        
        if kind == "operation_removed":
            if v1_op and not v2_op:
                verified.append(finding)
        
        elif kind == "parameter_became_required":
            param_name = finding["parameter"]
            v1_param = next((p for p in v1_op.get("parameters", []) 
                           if p["name"] == param_name), None)
            v2_param = next((p for p in v2_op.get("parameters", []) 
                           if p["name"] == param_name), None)
            
            if v1_param and v2_param and not v1_param.get("required") and v2_param.get("required"):
                verified.append(finding)
        
        elif kind == "schema_changed":
            param_name = finding["parameter"]
            v1_param = next((p for p in v1_op.get("parameters", []) 
                           if p["name"] == param_name), None)
            v2_param = next((p for p in v2_op.get("parameters", []) 
                           if p["name"] == param_name), None)
            
            # Only add if schemas actually differ
            if v1_param and v2_param and v1_param.get("schema") != v2_param.get("schema"):
                verified.append(finding)
    
    return verified