#!/usr/bin/env python3
"""Test Neo4j connection with different credentials"""

from neo4j import GraphDatabase
import os

# Common credential combinations to try
credentials_to_try = [
    ("neo4j", "neo4j"),
    ("neo4j", "password"), 
    ("neo4j", "expansion"),
    ("expansion", "expansion"),
    ("neo4j", ""),
]

uri = "bolt://localhost:7687"

print(f"Testing Neo4j connection to {uri}")
print("=" * 50)

for username, password in credentials_to_try:
    try:
        print(f"Trying username='{username}', password='{password}'...")
        driver = GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()
        print(f"✅ SUCCESS! Working credentials: username='{username}', password='{password}'")
        
        # Test a simple query
        with driver.session() as session:
            result = session.run("RETURN 'Hello Neo4j!' as message")
            message = result.single()["message"]
            print(f"   Test query result: {message}")
        
        driver.close()
        print(f"\nUpdate your .env file with:")
        print(f"NEO4J_USERNAME={username}")
        print(f"NEO4J_PASSWORD={password}")
        break
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        
else:
    print("\n❌ None of the common credentials worked.")
    print("Please check your Neo4j instance credentials or reset them.")
    print("\nTo reset Neo4j credentials:")
    print("1. Stop Neo4j")
    print("2. Delete the data directory")
    print("3. Restart with: docker run -p 7474:7474 -p 7687:7687 --env NEO4J_AUTH=neo4j/expansion neo4j:latest")