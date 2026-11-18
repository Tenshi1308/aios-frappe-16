import { computed, inject, reactive } from "vue";
import { useRoute, useRouter, type RouteLocationNormalizedLoaded } from "vue-router";
import { DESKTOP_WINDOW } from "@/features/desktop/context";

/**
 * Rute "milik halaman". Mode web: sama dengan useRoute(). Mode desktop: halaman berada di jendela, sedangkan
 * rute global adalah /desktop — maka name/path/query diambil dari rute jendela tersebut.
 * Pakai ini (bukan useRoute) di halaman yang membaca route.path / route.query / route.name.
 */
export function usePageRoute(): Pick<RouteLocationNormalizedLoaded, "name" | "path" | "query" | "params" | "fullPath"> {
  const route = useRoute();
  const win = inject(DESKTOP_WINDOW, null);
  if (!win) return route;
  const router = useRouter();
  const resolved = computed(() => router.resolve({ name: win.routeName.value, query: win.query.value }));
  return reactive({
    name: computed(() => resolved.value.name),
    path: computed(() => resolved.value.path),
    query: computed(() => resolved.value.query),
    params: computed(() => resolved.value.params),
    fullPath: computed(() => resolved.value.fullPath),
  }) as unknown as RouteLocationNormalizedLoaded;
}
