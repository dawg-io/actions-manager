/**
 * The removal routes answer a structured 502 when only some repositories could
 * be reached: `detail` is `{message, errors[]}` rather than a string. Assigning
 * it straight to a string renders "[object Object]".
 *
 * One parser for one backend contract — custom files and rulesets both read it,
 * and two copies drifted apart the moment either gained a field.
 */
export const apiErrorMessage = (error: unknown, fallback: string): string => {
  const detail = (error as {
    response?: { data?: { detail?: string | { message?: string; errors?: string[] } } };
  })?.response?.data?.detail;

  if (typeof detail === 'string') return detail;
  if (detail?.message) {
    return detail.errors?.length ? `${detail.message}: ${detail.errors.join('; ')}` : detail.message;
  }
  return fallback;
};
