from firebase_admin import firestore, credentials
import firebase_admin
import os
import logging

logger = logging.getLogger(__name__)

def get_company_config(company_id: str):
    """
    Retrieves the configuration for a company from Firebase Firestore.
    """
    # Ensure app is initialized (idempotent)
    if not firebase_admin._apps:
        try:
            # Intentar cargar desde el archivo service-account.json si existe
            sa_path = os.path.join(os.path.dirname(__file__), "../service-account.json")
            if os.path.exists(sa_path):
                cred = credentials.Certificate(sa_path)
                firebase_admin.initialize_app(cred)
                logger.info("[FIREBASE] Initialized with service-account.json")
            else:
                # Fallback a credenciales por defecto (Cloud Run)
                firebase_admin.initialize_app()
                logger.info("[FIREBASE] Initialized with default credentials")
        except Exception as e:
            logger.error(f"[FIREBASE] Failed to initialize: {e}")
            return {"error": f"Firebase initialization failed: {e}"}
        
    firestore_db = firestore.client()
    try:
        # Buscamos en la colección clientIDs donde el array 'ids' contenga el company_id
        docs = firestore_db.collection(u'clientIDs').where(u'ids', u'array_contains', company_id).get()
    except Exception as e:
        logger.error(f"[FIREBASE] Database connection failed: {e}")
        return {"error": f"[ERROR] Database connection failed: {e}"}
    
    if not docs:
        logger.warning(f"[FIREBASE] No config found for company_id: {company_id}")
        return None
        
    return docs[0].to_dict()
