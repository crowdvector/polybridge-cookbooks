# US Macro News to Forecast

Turn a US macro news story into a clear economic question, a quantitative
PolyBridge forecast, and a draft post for X.

## What it does

```text
News story → question → forecast → post
```

This is one workflow you can build with PolyBridge. Send a built-in example ID,
public article URL, pasted text, or UTF-8 text file to:

```text
POST https://api.polybridge.ai/v1/demos/us-macro-news-to-forecast
```

The all-in-one endpoint interprets the story, chooses a supported economic
question, runs the corresponding fixed US Macro forecast, and returns the
quantitative result and draft. You do not separately wire an LLM to PolyBridge.
The forecast model—not the story analysis—supplies the number.

Built-in examples are resolved by the API from their IDs; the client does not
send article text, fetch publisher URLs, or bundle article bodies.

This demo uses a fixed model so the article examples remain reproducible.

The response may include an X draft and Web Intent URL for review. The client
never posts to X. It opens the intent only after an explicit `y` in an
interactive terminal, and publishing still requires the user to choose
**Post** in X. Non-interactive and `--json` runs never open a browser.

## Quick start

The fastest way to try a public article URL is:

```bash
curl https://api.polybridge.ai/v1/demos/us-macro-news-to-forecast \
  -H "Content-Type: application/json" \
  -d '{"source":{"kind":"url","url":"https://example.com/news-story"}}'
```

This calls the complete demo endpoint and returns the selected question,
forecast, and draft post. To use the bundled Python client, install it with
Python 3.10+:

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/us-macro-news-to-forecast
bash setup.sh
python3 us_macro_news_to_forecast.py --demo inflation-ap
```

A PolyBridge API key is optional where anonymous access is enabled. To use one:

```bash
export POLYBRIDGE_API_KEY="your-key"
python3 us_macro_news_to_forecast.py --demo jobs-axios
```

The key is never printed or saved. Add `--json` for the complete public API
response on stdout. Normal terminal runs save a public-safe audit artifact in
`outputs/`; JSON runs write one only when `--output PATH` is supplied.

## Try one of the 3 examples

Each command sends only `{"source":{"kind":"example","id":"..."}}`.

### Inflation

Associated Press · 2026-08-12

- Article: [Inflation slows but prices remain elevated as Iran war and spending on AI push up prices](https://apnews.com/article/consumer-prices-inflation-fed-interest-rates-150e179a6c6b3182ba05cedf0188394b)
- Relationship: direct
- Selected question: What are the chances US headline inflation rises above 4% at any point from September through December 2026?
- Result: **18.4%** probability (path-hit forecast)

Draft for X:

> Inflation has eased, but price pressures haven't disappeared.
>
> Did America declare victory over inflation too soon?
>
> PolyBridge puts the chance of US headline inflation rising above 4% at any point from September through December at 18.4%.
>
> https://apnews.com/article/consumer-prices-inflation-fed-interest-rates-150e179a6c6b3182ba05cedf0188394b

```bash
python3 us_macro_news_to_forecast.py --demo inflation-ap
```

### Jobs

Axios · 2026-08-07

- Article: [U.S. economy surprisingly lost 23,000 jobs in July](https://www.axios.com/2026/08/07/july-jobs-report-employment-losses)
- Relationship: direct
- Selected question: How high does PolyBridge expect the US unemployment rate to get between September 2026 and March 2027?
- Result: **4.93%** peak unemployment (maximum across the window)

Draft for X:

> The US unexpectedly lost 23,000 jobs in July.
>
> Does the wider jobs market weaken too?
>
> PolyBridge expects unemployment to peak around 4.93% by the end of March '27.
>
> https://www.axios.com/2026/08/07/july-jobs-report-employment-losses

```bash
python3 us_macro_news_to_forecast.py --demo jobs-axios
```

### Treasury markets

The Guardian · 2026-08-19

- Article: [US treasury doubles debt buyback to steady bond market amid inflation fears](https://www.theguardian.com/business/2026/aug/19/us-treasury-doubles-debt-buyback-bond-market)
- Relationship: related
- Selected question: How strong does PolyBridge expect US economic growth to be in the fourth quarter of 2026?
- Result: **2.37%** annualized percentage change in real GDP during Q4 2026
- Relationship note: The story helped choose the question. It did not update the model.

Draft for X:

> Treasury is doubling long-end buybacks as pressure remains in bond markets.
>
> How much does the economy slow?
>
> PolyBridge's baseline for Q4 US real GDP growth is 2.37%.
>
> https://www.theguardian.com/business/2026/aug/19/us-treasury-doubles-debt-buyback-bond-market

```bash
python3 us_macro_news_to_forecast.py --demo treasury-markets-guardian
```

The Treasury-markets example is related rather than direct: the story helps
select a clear GDP-growth question, but it does not update the frozen model.

## Run your own article

Let the API retrieve a public HTTPS article:

```bash
python3 us_macro_news_to_forecast.py \
  --url "https://example.com/macro-story"
```

Or provide story text with optional attribution:

```bash
python3 us_macro_news_to_forecast.py \
  --text "A sufficiently detailed US macro story goes here." \
  --publisher "Example News" \
  --title "Example macro headline" \
  --source-url "https://example.com/macro-story"
```

You can also read UTF-8 text from a file:

```bash
python3 us_macro_news_to_forecast.py \
  --file story.txt \
  --source-url "https://example.com/macro-story"
```

`--demo`, `--url`, `--text`, and `--file` are mutually exclusive. URL mode
supports public HTTPS HTML; use text or file mode when extraction is not
available. Submit only content you are permitted to use.

For custom stories, the endpoint keeps the primary result readable: it does not
headline the financial-conditions index or housing starts while their public
interpretation is unsuitable. Treasury, bond-market, borrowing-cost, or debt
stories may instead select a related GDP-growth question. Direct CPI, jobs,
wages, spending, manufacturing, and rate stories keep a relevant clear target.

## Adapt the pattern

Use this example as a starting point for your own workflow:

- news story → forecast → X post
- market alert → forecast → Slack
- data release → forecast → research note
- internal trigger → forecast → dashboard

The client sends one request, validates and renders the response, optionally
saves a redacted artifact, and offers a review-only X intent. It does not retry
automatically after an ambiguous failure. See [`PROMPT.md`](PROMPT.md) for the
concise agent flow and
[`golden_examples.json`](golden_examples.json) for the public example metadata.
