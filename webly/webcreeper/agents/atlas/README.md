# Atlas

## Overview
Atlas is a powerful agent designed to crawl the web or a specific website and construct a graph representation of its structure. In this graph, webpages are represented as nodes, and the links between these webpages are represented as edges. 

## Key Features
- **Web Graph Construction**: Crawl a website and build a graph that visualizes its structure.
- **Scalability**: Capable of handling websites of varying sizes and complexities.
- **Customizable Settings**: Configure settings such as crawling depth, allowed domains, and user-agent.

## Future Enhancements
- **Graph Visualization**: Plan to include tools to visualize the constructed graphs for easier understanding and analysis.
- **Querying Routes**: Enable queries to determine specific routes to reach sections within a website.
- **Structural Insights**: Allow users to ask questions about the website's structure and receive meaningful insights.

## Usage

To use the **Atlas** agent, follow these steps:

### 1. Install the necessary dependencies
check the requirements.txt

```powershell
pip install -r requirements.txt
```

### 2. Import the Atlas agent
Import the Atlas agent into your script from the appropriate path.
```python
from agents.atlas.atlas import Atlas
```
### 3. Define the settings
Create a settings dictionary to configure the Atlas agent. This dictionary can include parameters like the allowed domains, maximum crawl depth, storage path, and user agent. For more settings check the ```creeper_core/base_agent.py```
```python
settings = {
    'allowed_domains': ['example.com'],  # Only allow crawling to example.com
    'max_depth': 2,  # Crawl up to depth 2
    'storage_path': './data',  # Path where the graph will be saved
    'user_agent': 'WebCreeper'  # Custom User-Agent to avoid blocking (Default is Atlas)
}
```

### 4. Create an instance of the Atlas agent
Instantiate the Atlas agent with the settings you defined earlier.
```python
atlas = Atlas(settings=settings)
```
### 5. Start the crawling process
Provide a starting URL (e.g., the homepage of the website) and call the crawl() method to begin crawling.
```python
start_url = "https://example.com"
atlas.crawl(start_url)
```
### 6. Access the crawled graph data
Once the crawl is complete, you can retrieve the constructed graph, which represents the website structure as a dictionary of nodes and edges.
```python
graph = atlas.get_graph() #You'll also find it saved in the data directory
```

## Contribution
Contributions to enhance Atlas or implement planned features are welcome.
