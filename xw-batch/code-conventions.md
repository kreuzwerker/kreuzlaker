# Best Practises and conventions for naming, processes,... in an AWS data stack with CDK

These are our conventions and rules for developing an AWS batch data stack in CDK. These rules are there to make your
life easier because they give us a common understanding how things should be, both to find/understand stuff and to build
long term maintainable code.

These rules made sense at the time of writing. They should make you think before you break them. They (together with the
code) should be adjusted if they do not make sense anymore.

Every rule should both explain what to do (and what not) and why this is advantages and should use examples if needed.

## AWS services

### Glue

See also the [Glue best practises](https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices.html)

- Use one crawler per table (=prefix in a bucket), as crawlers tend to "merge" different tables
  together ([make them partitions of one table](https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices.html#schema-crawlers-data-sources))
  if they are too similar.
- Try to avoid running crawlers, as they are expensive. E.g. a crawler only has to run if partitions change (e.g. if you
  partition by day, only run it once per day when the new partition arrives). If you know the schema use API calls to
  setup it (e.g. Glue jobs have a nice API for this).
- Do not use exclude patterns with crawlers (e.g. adding different file formats into the same prefix, but only using one
  for the table), as Athena does not use such patterns and would result in errors.
- Do not mix multiple schemas into the same s3 bucket prefix, use different prefixes. Glue databases work per prefix and
  e.g. Glue crawlers cannot recognise a common schema or Athena throws errors because it expects all files in a prefix have the
  same schema.