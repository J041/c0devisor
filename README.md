# code-visualizer

## Development

**Run with current working directory linked to the Docker container repo**
```
docker build -t codevisualizer . --no-cache
docker run  --rm -it -v ${PWD}:/app -p 6969:5000 codevisualizer
python3 app.py
```
- `codevisualizer` is the image name
- `--no-cache` is optional
- `- rm` flag creates a temporary container
- `- v` flag mounts \[source\]:\[directory to mount in container\]
- `- p` forwards port 5000 in docker container to port 6969 on localhost

Access the app using `http://localhost:6969/`

## Deployment
```
git clone https://github.com/J041/c0devisor.git

cd code-visualizer
sudo docker build -f Dockerfile.prod -t codevisualizer . --no-cache
sudo docker run -d -v ${PWD}:/app -p 6969:5000 codevisualizer
```

## more terminals
```
docker ps -a
docker exec -it <container-id>  /bin/bash
```

## usage guide

view [usage guide](./usage.md#usage-guide)
