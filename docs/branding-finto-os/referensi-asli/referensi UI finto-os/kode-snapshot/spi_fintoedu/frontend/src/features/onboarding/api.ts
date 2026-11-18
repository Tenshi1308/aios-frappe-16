import HttpClient from "@/helpers/http-client";

const API_BASE = "/api/method/spi_fintoedu.api.onboarding";

export interface OnboardingState {
  seen: string[];
  welcome_done: boolean;
}

export async function getOnboardingState(): Promise<OnboardingState> {
  const res = await HttpClient.get<{ message: OnboardingState }>(`${API_BASE}.get_onboarding_state`);
  return res.data.message;
}

export async function markGuideSeen(key: string): Promise<OnboardingState> {
  const res = await HttpClient.post<{ message: OnboardingState }>(`${API_BASE}.mark_guide_seen`, { key });
  return res.data.message;
}

export async function resetGuides(): Promise<OnboardingState> {
  const res = await HttpClient.post<{ message: OnboardingState }>(`${API_BASE}.reset_guides`);
  return res.data.message;
}
