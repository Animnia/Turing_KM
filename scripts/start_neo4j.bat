@echo off
echo Starting Neo4j Docker container...
docker run -d ^
    --name turing-neo4j ^
    -p 7474:7474 ^
    -p 7687:7687 ^
    -e NEO4J_AUTH=neo4j/turing2026 ^
    -v turing_neo4j_data:/data ^
    neo4j:5
echo Neo4j started! Browser: http://localhost:7474
echo Bolt: bolt://localhost:7687
echo User: neo4j / Password: turing2026
