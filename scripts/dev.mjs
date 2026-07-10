import { spawn, spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

// A resilient dev supervisor: Django and Vite are watched INDEPENDENTLY, so a crash in one — a
// failed `.mo` compile, a boot-time ImportError, a Vite hiccup — restarts only THAT process
// instead of tearing the whole dev environment down (the old dev.sh behaviour: `wait` returned on
// the first exit and the trap killed the other server too). Only an explicit shutdown (Ctrl-C /
// SIGTERM) stops everything, and it does a real process-TREE kill so no orphaned python/node
// processes or bound ports (:8000 / :5173) are left behind.
export function createSupervisor({
  exit = (code) => process.exit(code),
  warn = console.warn,
  env = process.env,
} = {}) {
  const children = new Set();
  const timers = new Set();
  let shuttingDown = false;

  function killTree(child) {
    if (!child || child.killed) {
      return;
    }
    // On Windows child.kill() signals only the direct child — but Django's autoreloader spawns a
    // grandchild (the actual server) and uv/vite sit under their own launchers, so a plain kill
    // orphans them and can leave the port bound. taskkill /T /F tears down the whole tree, and
    // spawnSync makes it finish BEFORE we exit.
    if (process.platform === "win32" && child.pid) {
      try {
        spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
        return;
      } catch {
        // fall through to the POSIX signal
      }
    }
    try {
      child.kill();
    } catch {
      // already gone
    }
  }

  function shutdown(exitCode = 0) {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    for (const timer of timers) {
      clearTimeout(timer);
    }
    timers.clear();
    for (const child of children) {
      killTree(child);
    }
    exit(exitCode);
  }

  // Keep `command` alive: (re)spawn it and, on any unexpected exit, schedule a respawn with
  // exponential backoff (capped). A run that stayed up longer than `healthyMs` resets the backoff.
  function supervise(name, command, args, { restartDelayMs = 500, maxDelayMs = 8000, healthyMs = 10000 } = {}) {
    let attempts = 0;

    const spawnOnce = () => {
      const startedAt = Date.now();
      let settled = false;
      const child = spawn(command, args, { env, stdio: "inherit" });
      children.add(child);

      const onGone = (reason) => {
        if (settled) {
          return; // 'error' + 'exit' can both fire; only react once
        }
        settled = true;
        children.delete(child);
        if (shuttingDown) {
          return;
        }
        if (Date.now() - startedAt >= healthyMs) {
          attempts = 0; // it was healthy; treat this as a fresh, first failure
        }
        attempts += 1;
        const delay = Math.min(maxDelayMs, restartDelayMs * 2 ** (attempts - 1));
        warn(`[dev] ${name} ${reason}; restarting in ${delay}ms...`);
        const timer = setTimeout(() => {
          timers.delete(timer);
          if (!shuttingDown) {
            spawnOnce();
          }
        }, delay);
        timers.add(timer);
      };

      child.on("exit", (code, signal) =>
        onGone(`exited (code ${code}${signal ? `, signal ${signal}` : ""})`),
      );
      child.on("error", (err) => onGone(`failed to start (${err && (err.code || err.message)})`));
      return child;
    };

    return spawnOnce();
  }

  return {
    children,
    supervise,
    shutdown,
    get shuttingDown() {
      return shuttingDown;
    },
  };
}

function main() {
  const supervisor = createSupervisor();
  process.on("SIGINT", () => supervisor.shutdown(0));
  process.on("SIGTERM", () => supervisor.shutdown(0));

  console.log("🚀 Starting development environment...");
  console.log("");

  console.log("Starting Django development server...");
  supervisor.supervise("Django", "uv", ["run", "manage.py", "runserver"]);

  // Run Vite directly through this node binary (not `npm run dev`) so there's no npm.cmd / shell
  // indirection to orphan on Windows. Vite reads host/port from vite.config.ts (:5173, strictPort).
  console.log("Starting Vite development server...");
  supervisor.supervise("Vite", process.execPath, ["node_modules/vite/bin/vite.js"]);
}

// Only start the real servers when run directly (`node scripts/dev.mjs`); stay inert when imported.
if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  main();
}
