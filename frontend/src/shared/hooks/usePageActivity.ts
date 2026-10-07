import {useEffect, useState} from "react";

// Keep retained editors mounted while suspending reads in hidden pages.
export function usePageActivity(active = true) {
  const [visible, setVisible] = useState(() => document.visibilityState !== "hidden");
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", update);
    update();
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return active && visible;
}
