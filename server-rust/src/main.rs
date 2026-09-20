use std::sync::Arc;
use clap::{Parser, Subcommand};
use tokio::sync::RwLock;
use tracing::{error, info, Level};
use tracing_subscriber::FmtSubscriber;

mod db;
mod protocol;
mod state;
mod tcp;
mod udp;

use db::Database;
use state::ServerState;

#[derive(Parser, Debug)]
#[command(name = "vimcord-server", version = "0.1.0", about = "High-Performance VimCord Server in Rust")]
struct Cli {
    #[arg(long, default_value = "0.0.0.0", help = "Host address to bind")]
    host: String,

    #[arg(long, default_value_t = 9988, help = "TCP control port")]
    tcp_port: u16,

    #[arg(long, default_value_t = 9989, help = "UDP voice & screen port")]
    udp_port: u16,

    #[arg(long, default_value = "vimcord_data.db", help = "Path to SQLite database file")]
    db: String,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand, Debug)]
enum Commands {
    #[command(about = "Manage users and database")]
    Manage {
        #[command(subcommand)]
        action: ManageAction,
    },
}

#[derive(Subcommand, Debug)]
enum ManageAction {
    #[command(about = "List all registered users")]
    List,
    #[command(about = "Create a new user account")]
    Add {
        username: String,
        password: String,
    },
    #[command(about = "Reset user password")]
    Passwd {
        user: String,
        new_password: String,
    },
    #[command(about = "Delete a user account")]
    Delete {
        user: String,
    },
    #[command(about = "Show server statistics")]
    Stats,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    // Initialize structured logging
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .with_target(false)
        .finish();
    let _ = tracing::subscriber::set_global_default(subscriber);

    let database = Arc::new(Database::new(&cli.db)?);

    // Handle management subcommands if invoked
    if let Some(Commands::Manage { action }) = cli.command {
        match action {
            ManageAction::List => {
                let users = database.get_all_users();
                println!("\n{}", "=".repeat(70));
                println!("Всего пользователей в базе: {}", users.len());
                println!("{}", "=".repeat(70));
                println!("{:<20} | {:<18} | {:<12} | Статус", "User ID", "Username", "Отображаемое");
                println!("{}", "-".repeat(70));
                for u in users {
                    println!("{:<20} | {:<18} | {:<12} | {}", u.user_id, u.username, u.display_name, u.status_text);
                }
                println!("{}\n", "=".repeat(70));
            }
            ManageAction::Add { username, password } => {
                match database.register_user(&username, &password, None) {
                    Ok(u) => println!("[УСПЕХ] Пользователь '{}' успешно создан! ID: {}", u.username, u.user_id),
                    Err(e) => eprintln!("[ОШИБКА] Не удалось создать пользователя: {}", e),
                }
            }
            ManageAction::Passwd { user, new_password } => {
                let target_uid = if let Some(u) = database.get_user_by_id(&user) {
                    Some(u.user_id)
                } else {
                    database.get_user_by_username(&user).map(|u| u.user_id)
                };

                match target_uid {
                    Some(uid) => match database.admin_set_password(&uid, &new_password) {
                        Ok(true) => println!("[УСПЕХ] Пароль для пользователя '{}' успешно изменен.", user),
                        _ => eprintln!("[ОШИБКА] Не удалось изменить пароль."),
                    },
                    None => eprintln!("[ОШИБКА] Пользователь '{}' не найден в базе.", user),
                }
            }
            ManageAction::Delete { user } => {
                let target_uid = if let Some(u) = database.get_user_by_id(&user) {
                    Some(u.user_id)
                } else {
                    database.get_user_by_username(&user).map(|u| u.user_id)
                };

                match target_uid {
                    Some(uid) => {
                        database.delete_user(&uid);
                        println!("[УСПЕХ] Пользователь '{}' успешно удален.", user);
                    }
                    None => eprintln!("[ОШИБКА] Пользователь '{}' не найден в базе.", user),
                }
            }
            ManageAction::Stats => {
                let (u, r, c, m) = database.get_stats();
                println!("\n{}", "=".repeat(40));
                println!(" Статистика сервера VimCord (Rust)");
                println!("{}", "=".repeat(40));
                println!(" Зарегистрированных пользователей : {}", u);
                println!(" Созданных серверов (комнат)     : {}", r);
                println!(" Каналов                          : {}", c);
                println!(" Сообщений в истории             : {}", m);
                println!("{}\n", "=".repeat(40));
            }
        }
        return Ok(());
    }

    println!(
        r#"
==================================================
  🎙️ VimCord Server (High-Performance Rust)
  TCP Control Port: {}
  UDP Voice Port:   {}
  Bind Host:        {}
  Database:         {}
==================================================
"#,
        cli.tcp_port, cli.udp_port, cli.host, cli.db
    );

    let state = Arc::new(RwLock::new(ServerState::new(database)));

    let udp_state = state.clone();
    let udp_host = cli.host.clone();
    let udp_port = cli.udp_port;
    let udp_handle = tokio::spawn(async move {
        if let Err(e) = udp::run_udp_server(udp_state, &udp_host, udp_port).await {
            error!("UDP server fatal error: {}", e);
        }
    });

    let tcp_state = state.clone();
    let tcp_host = cli.host.clone();
    let tcp_port = cli.tcp_port;
    let tcp_handle = tokio::spawn(async move {
        if let Err(e) = tcp::run_tcp_server(tcp_state, &tcp_host, tcp_port).await {
            error!("TCP server fatal error: {}", e);
        }
    });

    tokio::select! {
        res = udp_handle => {
            if let Err(e) = res {
                error!("UDP task terminated unexpectedly: {}", e);
            }
        }
        res = tcp_handle => {
            if let Err(e) = res {
                error!("TCP task terminated unexpectedly: {}", e);
            }
        }
        _ = tokio::signal::ctrl_c() => {
            info!("Received shutdown signal. Stopping VimCord Server...");
        }
    }

    info!("VimCord Server shutdown complete.");
    Ok(())
}
