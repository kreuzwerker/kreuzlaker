# xw-batch dbt - dbt transformation for the xw batch stack

### Initial Setup

* Install dbt with poetry: `poetry install` and activate the venv: `poetry shell` (dbt installed via brew will not work
  as it misses the athena dbt integration)
* Make sure you have valid credentials for your aws account. E.g. sign on via `aws sso login`
* To test if the login worked execute `aws sts get-caller-identity` (should show your credentials) and
  `aws s3 ls s3://<query result bucket name>/users/user_<aws username>/` (should show files or an error message that
  this prefix does not exist) (Note: no `--profile` allowed! Use `AWS_PROFILE` environment variable if needed)
* Setup a `~/.dbt/profiles.yml`:

```yaml
# https://docs.getdbt.com/reference/profiles.yml
config:
  # dbt gathers anonymous usage data -> disable that
  send_anonymous_usage_stats: false

# Name needs to be the same as in dbt/xw_batch/dbt_project.yml
xw_batch:
  outputs:
    # name: see below the "target: " line
    dev:
      # The prefix of the final schemas (dbt concats this and the ones configured in dbt_project.yml)
      # adjust with your name, make sure the final concatted value is a valid identifier, so no dots!
      # user_ is a must!
      schema: user_<name>
      # aws username as is, including dots, etc!
      s3_staging_dir: s3://<query result bucket name>/users/user_<aws username>/
      database: awsdatacatalog
      region_name: eu-central-1
      work_group: all_users
      type: athena
      # 1 assumes that if it breaks, it breaks because there is an error
      num_retries: 1
      # seconds -> if this is big, we will always wait for this line per task 
      poll_interval: 1
      # How many sql queries will run in parallel
      threads: 4
  target: dev
```

Adjust `schema: user_<name>` to contain your name, e.g. `schema: user_jankatins` (**MUST be a valid object 
identifier, so no dots!**) => these will show up as databases in the glue catalog, so whatever you do will not interfere
with production tables. Credentials will automatically be used from the default credential chain, i.e. whatever you
setup as default credentials (or using the profile from the `AWS_PROFILE` env variable).

## Using the project

Try running the following commands:

- `cd dbt/xw_batch`  will cd into the folder with the dbt project
- `dbt deps` installs the required additional packages
- `dbt run` will run all transformations
- `dbt test` will run all data tests
- `dbt docs generate && dbt docs serve` will compile and then serve the data documentations
  in [http://127.0.0.1:8080/](http://127.0.0.1:8080/)

## Folder structure
in the dbt project folder (`dbt/xw_batch`):

* `models/prep/*`: transformations for intermediate tables/views -> Cleaning, aggregating, etc
* `models/datasets/*`: transformations for final tables which are fit for consumption

## Workflow for queries

* New sql queries must be added into `models/datasets` or `models/prep`. Only `models/datasets` will be
  exposed to BI Tools.
    * It is recommended to perform a clean step of the data in `models/prep` and apply the business logic
      in `models/datasets`.
    * The name of the file is the name of the table later, e.g. `models/customer.sql` will be called `customer`.
      Since just the file name is used, the table names have to be unique across the `models` and the `prep`
      directories.
    * If you want to add new directories to `models`, make sure you also add them into `dbt_project.yml`.
* Execute `dbt run` (in the dbt directory) for running the whole pipeline or `dbt run -s <table-name>` for a single
  one (e.g. run to failure and then iterating on a fix)
* Format the sql+jinja code with `sqlfluff fix` and lint via `sqlfluff lint` (in the dbt directory)
* The result can be seen in the `AWS Athena` e.g. in the console. If your table name is `prep_test` then
  execute `select * from prep_test;`.

## Resources:

- How to [structure a dbt project](https://discourse.getdbt.com/t/how-we-structure-our-dbt-projects/355)
- [Best practises](https://docs.getdbt.com/docs/guides/best-practices)
- [Code conventions](https://github.com/dbt-labs/corp/blob/master/dbt_style_guide.md)

=> this repo tried to follow these guides as good as possible, but there is probably room for improvements and
evolution.

More resources:

- The [gitlab dbt guide](https://about.gitlab.com/handbook/business-technology/data-team/platform/dbt-guide/) is quite
  extensive (some more resources: ["How they dbt"](https://github.com/stumelius/howtheydbt/blob/main/README.md))
  their [dbt code available as well](https://gitlab.com/gitlab-data/analytics/-/blob/master/transform/snowflake-dbt/)
- [Basics of data modeling](https://www.linkedin.com/pulse/things-i-learned-data-modelling-martin-loetzsch/): best
  practices for deriving analytical entities from business questions and a mental model / metaphor for designing data
  sets / cubes.
- Learn more about dbt [in the docs](https://docs.getdbt.com/docs/introduction)
- Check out [Discourse](https://discourse.getdbt.com/) for commonly asked questions and answers
- Join the [chat](https://community.getdbt.com/) on Slack for live discussions and support
- Find [dbt events](https://events.getdbt.com) near you
- Check out [the blog](https://blog.getdbt.com/) for the latest news on dbt's development and best practices

## Todo

- Add some more transformations and tests
- Setup and automate the deployment
- Figure out how to prevent stakeholders seeing bad data (red-blue deployment are not so easy with athena :-()
- Implement notification for failures in the production pipeline or tests
- Figure out a way to deploy the dbt docs (`dbt docs generate` generates static files)