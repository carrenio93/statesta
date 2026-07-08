create schema if not exists raw;

create table raw.api_responses (
    id                bigint generated always as identity primary key,
    source            text        not null default 'api_football',
    endpoint          text        not null,
    request_params    jsonb       not null default '{}'::jsonb,
    http_status       integer,
    response_body     jsonb       not null,
    response_hash     text,
    source_fetched_at timestamptz not null default now(),
    created_at        timestamptz not null default now()
);

create index ix_raw_api_responses_endpoint_fetched
    on raw.api_responses (endpoint, source_fetched_at desc);

create index ix_raw_api_responses_params
    on raw.api_responses using gin (request_params);
