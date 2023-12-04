pipenv run python get_plugins.py

pipenv run mkdocs gh-deploy

git pull
git add .
git commit -m "update"
git push