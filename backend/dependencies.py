import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

# Setup logger
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Support both MONGO_DETAILS and MONGO_URI for flexibility
# MONGO_DETAILS is preferred, but fall back to MONGO_URI if not set
MONGO_DETAILS = os.getenv("MONGO_DETAILS") or os.getenv("MONGO_URI")
MONGO_DATABASE_NAME = os.getenv("MONGO_DATABASE_NAME", "litecoin_rag_db") # Default DB name
CMS_ARTICLES_COLLECTION_NAME = os.getenv("CMS_ARTICLES_COLLECTION_NAME", "cms_articles") # Default collection

# Global MongoDB client instance to avoid reconnecting on every request
# This should ideally be managed by the FastAPI app lifecycle (startup/shutdown events)
# For now, simple global client for the dependency.
mongo_client: AsyncIOMotorClient = None

async def get_mongo_client() -> AsyncIOMotorClient:
    global mongo_client
    if mongo_client is None:
        if not MONGO_DETAILS:
            raise ConnectionError("MONGO_DETAILS or MONGO_URI environment variable must be set.")
        try:
            # Log connection attempt without exposing full connection string (may contain credentials)
            logger.info("Attempting to connect to MongoDB")
            # Configure connection pool settings to prevent connection leaks
            mongo_client = AsyncIOMotorClient(
                MONGO_DETAILS,
                maxPoolSize=50,
                minPoolSize=5,
                maxIdleTimeMS=30000,
                serverSelectionTimeoutMS=5000,
                retryWrites=True,
                retryReads=True
            )
            # Verify connection
            await mongo_client.admin.command('ping') 
            logger.info("Successfully connected to MongoDB with connection pooling configured")
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            mongo_client = None # Reset on failure
            raise ConnectionError(f"Failed to connect to MongoDB: {e}")
        except Exception as e: # Catch other potential errors during client creation
            logger.error(f"An unexpected error occurred during MongoDB client initialization: {e}", exc_info=True)
            mongo_client = None
            raise ConnectionError(f"An unexpected error occurred: {e}")
    return mongo_client

async def get_cms_db() -> AsyncIOMotorCollection:
    """
    Dependency function to get the MongoDB collection for CMS articles.
    """
    try:
        client = await get_mongo_client()
        if client is None:
            # This case should ideally be handled by get_mongo_client raising an error
            raise ConnectionError("MongoDB client is not available.")
        
        database = client[MONGO_DATABASE_NAME]
        cms_articles_collection = database[CMS_ARTICLES_COLLECTION_NAME]
        return cms_articles_collection
    except ConnectionError as e:
        # Re-raise connection errors to be handled by FastAPI or calling code
        raise e
    except Exception as e:
        # Catch any other unexpected errors during DB access
        logger.error(f"Error accessing CMS DB collection: {e}", exc_info=True)
        raise ConnectionError(f"Error accessing CMS DB collection: {e}")

USER_QUESTIONS_COLLECTION_NAME = os.getenv("USER_QUESTIONS_COLLECTION_NAME", "user_questions") # Default collection

async def get_user_questions_collection() -> AsyncIOMotorCollection:
    """
    Dependency function to get the MongoDB collection for logging user questions.
    """
    try:
        client = await get_mongo_client()
        if client is None:
            raise ConnectionError("MongoDB client is not available.")
        
        database = client[MONGO_DATABASE_NAME]
        user_questions_collection = database[USER_QUESTIONS_COLLECTION_NAME]
        return user_questions_collection
    except ConnectionError as e:
        raise e
    except Exception as e:
        logger.error(f"Error accessing user questions collection: {e}", exc_info=True)
        raise ConnectionError(f"Error accessing user questions collection: {e}")

LLM_REQUEST_LOGS_COLLECTION_NAME = os.getenv("LLM_REQUEST_LOGS_COLLECTION_NAME", "llm_request_logs") # Default collection

async def get_llm_request_logs_collection() -> AsyncIOMotorCollection:
    """
    Dependency function to get the MongoDB collection for logging LLM request/response data.
    """
    try:
        client = await get_mongo_client()
        if client is None:
            raise ConnectionError("MongoDB client is not available.")
        
        database = client[MONGO_DATABASE_NAME]
        llm_request_logs_collection = database[LLM_REQUEST_LOGS_COLLECTION_NAME]
        return llm_request_logs_collection
    except ConnectionError as e:
        raise e
    except Exception as e:
        logger.error(f"Error accessing LLM request logs collection: {e}", exc_info=True)
        raise ConnectionError(f"Error accessing LLM request logs collection: {e}")

KNOWLEDGE_CANDIDATES_COLLECTION_NAME = os.getenv("KNOWLEDGE_CANDIDATES_COLLECTION_NAME", "knowledge_candidates")

async def get_knowledge_candidates_collection() -> AsyncIOMotorCollection:
    """
    Dependency function to get the MongoDB collection for knowledge gap candidates.
    """
    try:
        client = await get_mongo_client()
        if client is None:
            raise ConnectionError("MongoDB client is not available.")
        
        database = client[MONGO_DATABASE_NAME]
        return database[KNOWLEDGE_CANDIDATES_COLLECTION_NAME]
    except ConnectionError as e:
        raise e
    except Exception as e:
        logger.error(f"Error accessing knowledge candidates collection: {e}", exc_info=True)
        raise ConnectionError(f"Error accessing knowledge candidates collection: {e}")


async def close_mongo_connection():
    """
    Closes the Motor MongoDB client connection.
    Should be called during application shutdown to prevent connection leaks.
    """
    global mongo_client
    if mongo_client:
        try:
            mongo_client.close()
            logger.info("Motor MongoDB connection closed")
        except Exception as e:
            logger.error(f"Error closing Motor MongoDB connection: {e}", exc_info=True)
        finally:
            mongo_client = None
