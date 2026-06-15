# Data Masking

Sensitive guest information is masked before being returned in the API response. Masking is applied after rule evaluation, meaning all validation rules operate on the original values.

The masked values are returned in the `masked_guest_data` field.

Raw guest data is never sent to the LLM. The LLM receives only rule findings and generic failure descriptions, without names, card numbers, booking references, membership IDs, or other personally identifiable information.

## Masking Rules

| Field | Strategy | Example |
|---|---|---|
| Guest name | First character retained for each word, remaining characters replaced with `*` | `Alice Johnson` → `A**** J******` |
| Passenger name | Same as guest name | `John Smith` → `J*** S****` |
| Card holder name | Same as guest name | `Jon Smith` → `J** S****` |
| Card number | All digits except the last four replaced with `*` | `4111111111111111` → `************1111` |
| Card expiry | Month masked, year retained | `08/28` → `**/28` |
| Booking reference | First two and last two characters retained | `BK-20260613-4421A` → `BK**************1A` |
| Flight PNR | Same as booking reference | `PNR-EK202-001` → `PN*********01` |
| QR code payload | Fully masked | `<any value>` → `****` |
| Airline status ID | First two and last two characters retained | `FF-987654321` → `FF********21` |

Fields that are not provided remain `null` in `masked_guest_data`.

`card_type` is not masked because it is a product category and does not identify an individual.

`transaction_id` is not masked because it is a system-generated identifier used for tracing and auditing and does not contain guest-sensitive information.
