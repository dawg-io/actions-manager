/**
 * The server's error payload from a rejected request, falling back to the
 * error's own message and then to the error itself.
 *
 * A plain cast rather than axios.isAxiosError: the shared manual mock in
 * src/__mocks__/axios.ts does not implement that guard, so calling it would
 * throw in every test that exercises a catch block.
 */
export const errorDetail = (error: unknown): unknown => {
  const e = error as { response?: { data?: unknown }; message?: string };
  return e?.response?.data || e?.message || error;
};
