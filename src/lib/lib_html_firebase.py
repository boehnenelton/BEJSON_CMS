"""
Library:      lib_html_firebase.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Integration layer for Firebase services (Firestore, Auth, Storage).
"""

import os
import json

def validate_firebase_config(config: dict):
    """Ensures all required Firebase parameters are present."""
    required = ["apiKey", "authDomain", "projectId", "storageBucket", "messagingSenderId", "appId"]
    missing = [key for key in required if not config.get(key) or config.get(key) == "MISSING"]
    if missing:
        raise RuntimeError(f"CRITICAL: Missing essential Firebase environment variables: {', '.join(missing)}")

# SECURITY: Hardcoded credentials removed. Use environment variables.
# Defaults removed to prevent information disclosure (Mandate: POL-SEC-004).
FIREBASE_CONFIG = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "projectId": os.getenv("FIREBASE_PROJECT_ID"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
    "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
    "appId": os.getenv("FIREBASE_APP_ID")
}

SDK_VERSION = "12.12.1"

def get_firebase_init_script(config, services=None):
    """
    Returns a <script type="module"> tag with Firebase initialization.
    config: dict containing Firebase project identifiers (Required)
    services: list of strings ['auth', 'firestore', 'analytics', 'performance']
    """
    if not config:
        raise ValueError("Firebase configuration 'config' is required.")
    
    validate_firebase_config(config)
        
    services = services or []
    cfg_json = json.dumps(config, indent=2)
    
    imports = [f'import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/{SDK_VERSION}/firebase-app.js";']
    
    init_logic = []
    
    if "auth" in services:
        imports.append(f'import {{ getAuth }} from "https://www.gstatic.com/firebasejs/{SDK_VERSION}/firebase-auth.js";')
        init_logic.append("  const auth = getAuth(app);")
        init_logic.append("  window.firebaseAuth = auth;")

    if "firestore" in services:
        imports.append(f'import {{ getFirestore }} from "https://www.gstatic.com/firebasejs/{SDK_VERSION}/firebase-firestore.js";')
        imports.append(f'import * as pipelines from "https://www.gstatic.com/firebasejs/{SDK_VERSION}/firebase-firestore-pipelines.js";')
        init_logic.append("  const db = getFirestore(app);")
        init_logic.append("  window.firestoreDb = db;")
        init_logic.append("  window.firestorePipelines = pipelines;")
        init_logic.append("  console.log('Firestore Pipelines (2026 Standard) loaded.');")

    imports_str = "\n  ".join(imports)
    init_logic_str = "\n".join(init_logic)

    script = f"""
<script type="module">
  {imports_str}

  const firebaseConfig = {cfg_json};

  // Initialize Firebase
  const app = initializeApp(firebaseConfig);
  console.log("Firebase initialized successfully:", app.name);
  
{init_logic_str}

  // Expose status to UI if badge exists
  const badge = document.getElementById('status-badge');
  if (badge) {{
      badge.textContent = "INITIALIZED";
      badge.style.backgroundColor = "#4CAF50";
      badge.style.color = "white";
  }}
</script>
"""
    return script

def get_firestore_pipeline_example():
    """
    Returns a string containing a 2026 standard Firestore Pipeline example.
    """
    return """
// 2026 Standard: Relational Join via Pipeline
const { field, variable } = window.firestorePipelines;
const db = window.firestoreDb;

const articlesWithAuthProfile = db.pipeline().collection("articles")
  .define(field("authorUid").as("author_id"))
  .addFields(
    db.pipeline().collection("users")
      .where(field("__name__").documentId().equal(variable("author_id")))
      .select(field("displayName"), field("avatarUrl"), field("handle"))
      .toScalarExpression()
      .as("author")
  );
"""
