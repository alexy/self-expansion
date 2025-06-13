import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load .env file with override=True to take precedence over system variables
load_dotenv(override=True)

# Configure for local Neo4j instance
# Default local Neo4j connection
URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

print(f"Connecting to Neo4j at: {URI}")
try:
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
    driver.verify_connectivity()
    print("✓ Neo4j connection successful")
except Exception as e:
    print(f"⚠️  Neo4j connection failed: {e}")
    print(f"   Make sure Neo4j is running at {URI}")
    print(f"   Default credentials: username='{USERNAME}', password='{PASSWORD}'")
    print("   You can start Neo4j with Docker: docker run -p 7474:7474 -p 7687:7687 --env NEO4J_AUTH=neo4j/password neo4j:latest")
    # Still create the driver object for when Neo4j becomes available
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
