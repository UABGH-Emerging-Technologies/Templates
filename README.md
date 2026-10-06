# MLOps and Web App: Template Framework for Traceable Machine Learning, Artificial Intelligence and Web Applications
This repository contains [copier templates](https://copier.readthedocs.io/en/stable/) for deploying MLOps infrastructure and web applications. Brought to you by the [Perioperative Data Science Team at the University of Alabama, Birmingham](https://sites.uab.edu/periop-datascience/).

## Setting up the Environment
The application was built and tested in a Windows Subsystem for Linux 2 (WSL2) environment.  The software should work in either a WSL2 or Linux environment. If you are using a Linux environment, skip the installation steps for WSL2.  While it is possible to get this tool to work without all these steps, we highly encourage users to install WSL2, Docker, and VSCode for the optimal experience using this software.

### Install WSL2 on Windows
  Follow the instructions for [installing WSL2](https://github.com/UABPeriopAI/Templates/wiki/Setting-up-WSL2).

### Install Git inside WSL2
Additionally, you may want to follow the [instructions for our recommended usage of git in WSL2](https://github.com/UABPeriopAI/Templates/wiki/Recommended-git-Usage-in-WSL2).

### Install Docker
Follow the instructions for [installing Docker](https://github.com/UABPeriopAI/Templates/wiki/Setting-up-Docker) from the MLOps Template repository Wiki.

### Install VSCode
Follow the instructions for [installing VSCode](https://github.com/UABPeriopAI/Templates/wiki/Installing-VSCode) from the MLOps Template repository Wiki.

## Copier Setup
If you are working in a Windows environment, first [install Windows Subsystem](https://learn.microsoft.com/en-us/windows/wsl/install) for Linux 2 (WSL 2).  This streamlines installation and makes porting projects to cloud or other environments easier.  See the project Wiki for additional installation and setup guidance.

In order to use this template, the  package must first be installed. You can test this by typing the following in the WSL 2 command line: 
~~~
copier --version
~~~ 



The output should look something like the following:
```
copier 9.10.2
```

If it's not already installed, you can do so with pipx or uv:
~~~
pipx install copier
~~~
or
~~~
uv tool install copier
~~~

## Usage
1. Before using the copier, create a new, empty repository for your project - you'll need the URL shortly.


2. With copier, you can call this repository directly from the command line.  This copier is designed to install the codebase and it automatically creates and relocates the data structure. The command to create a new project is: copier copy path/to/project/template path/to/destination

Examples of how to create a new project from these templates:
~~~
$ git clone https://github.com/UABPeriopAI/Templates.git
~~~
Then bootstrap git-tracked template sources (one-time per clone):
~~~
$ cd Templates
$ ./scripts/bootstrap_template_sources.sh
~~~
This initializes independent git histories (with a bootstrap tag) in `common/`, `fastapi_app/`, `gradio_app/`, and `mlops_app/`.
Then generate from one of the app templates:
~~~
$ copier copy --trust Templates/fastapi_app path/to/destination \
    -d common_template_src="$(realpath Templates/common)"
~~~
OR
~~~
$ copier copy --trust Templates/gradio_app path/to/destination \
    -d common_template_src="$(realpath Templates/common)"
~~~
OR
~~~
$ copier copy --trust Templates/mlops_app path/to/destination \
    -d common_template_src="$(realpath Templates/common)"
~~~
Note that the command will create the project inside the destination directory, not with the name of the destination directory.

### Human+agent coordination template (proposal)

`coordination/` stamps the human+agent project-board pattern into any project (new or existing): a shared GitHub Project board driven by both developers' coding agents (Claude Code, OpenCode, Codex, …) and humans, with cross-tool conventions in `AGENTS.md`, tool-neutral procedures in `process/`, and per-tool command wrappers. Apply it alongside any app template:
~~~
$ copier copy --trust Templates/coordination path/to/destination
~~~
then have a coding agent run the `board-setup` procedure to create and seed the board. See `coordination/README.md` for the pattern, adoption status, and migration checklist.

### Template Update Propagation
This repository now renders explicit Copier answer files so generated projects can be updated later:

- `fastapi_app` projects: `.copier-answers.fastapi.yml`
- `gradio_app` projects: `.copier-answers.gradio.yml`
- `mlops_app` projects: `.copier-answers.mlops.yml`
- shared `common` layer: `.copier-answers.common.yml`

To pull template changes into an existing generated project, run update from the project root:

~~~
# FastAPI projects
copier update --trust --defaults --skip-tasks -a .copier-answers.fastapi.yml
copier update --trust --defaults --skip-tasks -a .copier-answers.common.yml

# Gradio projects
copier update --trust --defaults --skip-tasks -a .copier-answers.gradio.yml
copier update --trust --defaults --skip-tasks -a .copier-answers.common.yml

# MLOps projects
copier update --trust --defaults --skip-tasks -a .copier-answers.mlops.yml
copier update --trust --defaults --skip-tasks -a .copier-answers.common.yml
~~~

Run both update commands for each project type: the first updates the app-specific template and the second updates shared content from `common/`.
`--skip-tasks` avoids rerunning repository/bootstrap side effects in template hooks.
`copier update` requires the target project repo to be clean before running.

If your project already has code in it, you'll need to merge whatever branch has existing code with the new one copier creates using 
~~~
$ git checkout <new branch>
$ git merge <old_branch> --allow-unrelated-histories
~~~

Executing this command will initiate prompts for you to enter project specific information.   Our template has the following inputs for a new project (with default values in parenthesis)
#### fastapi_app
- [ ] Project Name* (FastAPIapp) - Name of the new project. This parameter is used in a number of places and should be a title that the user can use to readily identify the project.
- [ ] Author Name* () - Name of the person creating the project. This will be used in project metadata and in git commit messages.
- [ ] Description () - Brief description of what the software is intended to do.
- [ ] Author Email* () - Be sure to use the email connected to your version control account.
- [ ] Repository URL* () - The empty git Repository URL for the new project from step 1.
- [ ] Data Directory* (data) - The folder where you plan to put the data (eventually we will move it there automatically, but for now this just updates the devcontainer.json so the Docker container knows where to find the data).
- [ ] Data directory* name (DATASCI)
- [ ] LLM endpoint () - Optional LLM endpoint string used by the template.
- [ ] Common template source () - Path or git URL for the `common` template source.
- [ ] MLflow Tracking URI (https://) - URI for MLflow tracking.

#### gradio_app
- [ ] Project Name* (GradioApp) - Name of the new project. This parameter is used in a number of places and should be a title that the user can use to readily identify the project.
- [ ] Author Name* () - Name of the person creating the project. This will be used in project metadata and in git commit messages.
- [ ] Description () - Brief description of what the software is intended to do.
- [ ] Author Email* () - Be sure to use the email connected to your version control account.
- [ ] Repository URL* () - The empty git Repository URL for the new project from step 1.
- [ ] Data Directory* (data) - The folder where you plan to put the data (eventually we will move it there automatically, but for now this just updates the devcontainer.json so the Docker container knows where to find the data).
- [ ] Data directory* name (DATASCI)
- [ ] LLM endpoint () - Optional LLM endpoint string used by the template.
- [ ] Common template source () - Path or git URL for the `common` template source.
- [ ] MLflow Tracking URI (https://) - URI for MLflow tracking.

#### mlops_app
- [ ] Project Name* (ML_Project) - Name of the new project. This parameter is used in a number of places and should be a title that the user can use to readily identify the project.
- [ ] Author Name* () - Name of the person creating the project. This will be used in project metadata and in git commit messages.
- [ ] Description (This ML/AI is designed to ) - Brief description of what the software is intended to do.
- [ ] Author Email* () - Be sure to use the email connected to your version control account.
- [ ] Repository URL* () - The empty git Repository URL for the new project from step 1.
- [ ] Data Directory* (data) - The folder where you plan to put the data (eventually we will move it there automatically, but for now this just updates the devcontainer.json so the Docker container knows where to find the data).
- [ ] Data directory* name (DATASCI)
- [ ] Common template source () - Path or git URL for the `common` template source.
- [ ] MLflow Tracking URI (https://) - URI for MLflow tracking.

#### gradio_app
- [ ] Project Name* (GradioApp) - Name of the new project. This parameter is used in a number of places and should be a title that the user can use to readily identify the project.
- [ ] Author Name* () - Name of the person creating the project. This will be used in the setup.py file and in git commit messages.
- [ ] Description () - Brief description of what the software is intended to do.
- [ ] Author Email* () - Be sure to use the email connected to your version control account.
- [ ] Repository URL* () - The empty git Repository URL for the new project from step 1.
- [ ] Data Directory* (data) - The folder where you plan to put the data.
- [ ] Data directory* name (DATASCI)
- [ ] LLM endpoint () - Optional LLM endpoint string used by the template.
- [ ] Common template source () - Source path or git URL for the common template (auto-detected by default).
- [ ] MLflow Tracking URI (https://) - URI for MLflow tracking.

A * next to the parameter indicates a field that is required for the template to deploy as intended. Many default values are left blank, because we make no presumptions about the specific information for a project. We encourage users to provide input for all fields, although *Description* is not required for the template to deploy correctly. 

##### After running the copier
+ The contents of the template are pushed to a new repository branch "feature/initialize_template" which is ready to merge to main. Additionally, there will be a remnant master branch that can be deleted (copier creates a master branch, but our group prefers the name 'main'.)

+ The data directory will be automatically created and moved to Data_Directory/Data_Directory_name/

+ *Note:* The post_gen_project.sh script sometimes generates an error even after successful deployment of the template.  


##### Troubleshooting
Depending on the repository for the new project, users may have to setup programmatic access to the repository.  For example, GitHub requires use of a personal access token to programmatically access repositories.  Users can follow the instructions [here](https://stackoverflow.com/questions/68775869/message-support-for-password-authentication-was-removed)
to setup a personal access token on GitHub and integrate it into their operating system (via Windows Credential Manager, for example.)

Disclosure: This template may not work out of the box in every environment, but the contents of the template can be modified, the Docker parameters in particular, to get it working. 




