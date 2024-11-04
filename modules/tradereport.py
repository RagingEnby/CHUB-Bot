from typing import Optional, Literal, Any
import aiohttp
import disnake
import aiofiles
import json
import asyncio

from modules import mojang
from modules import misc

import datatypes
import config

BUTTON_ID = 'TradeReport'


PENDING_REPORTS: dict[str, datatypes.TradeReport] = {
    id_: datatypes.TradeReport.from_dict(trade)
    for id_, trade in json.load(open(config.TRADE_REPORT_FILE_PATH, 'r')).items()
}
# this is just here becauase i use this to stop multi-sending at the very last chance it has
SENT_REPORTS: list[str] = []
# this is no longer used, but its here for the future if needed
INACTIVE_COMPONENTS: list[disnake.ui.Button] = [
    disnake.ui.Button(
        label="Accept",
        style=disnake.ButtonStyle.green,
        disabled=True
    ),
    disnake.ui.Button(
        label="Deny",
        style=disnake.ButtonStyle.red,
        disabled=True
    )
]


async def upload_image(url: str, session: aiohttp.ClientSession) -> datatypes.TradeReportAttachment:
    response = await session.post(
        'https://api.ragingenby.dev/download',
        params={
            "key": config.RAGINGENBY_API_KEY
        },
        json={
            "url": url
        }
    )
    return datatypes.TradeReportAttachment.from_dict(await response.json())


async def save_pending_reports():
    async with aiofiles.open(config.TRADE_REPORT_FILE_PATH, 'w') as file:
        await file.write(json.dumps({k: v.to_dict() for k, v in PENDING_REPORTS.items()}))


async def log_trade_report(report: datatypes.TradeReport):
    PENDING_REPORTS[report.id] = report
    await save_pending_reports()


async def log_trade_report_completion(report: datatypes.TradeReport) -> bool:
    report = PENDING_REPORTS.pop(report.id, None) # type: ignore
    if report:
        await save_pending_reports()
    return bool(report)


async def on_button_click(inter: disnake.MessageInteraction, button_data: str):
    # im FULLY aware this is a bad and long function. i just cba to make it better
    # if it works it works :shrug:
    button_data: dict[str, Any] = json.loads(button_data)
    trade_report: Optional[datatypes.TradeReport] = PENDING_REPORTS.get(button_data['id'])
    if trade_report is None:
        return await inter.send(embed=misc.make_error(
            "Invalid Trade",
            f"No trade with the ID `{button_data['id']}`. This is likely because the trade has already been accepted or denied"
        ), ephemeral=True)
    author = inter.bot.get_user(trade_report.author) if trade_report.author else None
    
    if button_data['action'] != 'accept':
        await inter.message.delete()
        await log_trade_report_completion(trade_report)
        if author:
            try:
                await author.send(embed=misc.make_error(
                    "Trade Report Denied",
                    "Your trade report has been denied. For more information, open up a ticket at https://discord.com/channels/934240413974417439/1258100866804875264/1258101752054681702"
                ))
            except Exception as e:
                print('error trying to dm', author, '-', e)
        return await inter.send(embed=misc.make_success(
            "Success",
            "The trade report has been denied and the author has been notified"
        ))

    
    await inter.response.send_modal(
        title="Send Trade Report",
        custom_id="send_trade_report",
        components=[
            disnake.ui.TextInput(
                label="Date",
                custom_id="date",
                style=disnake.TextInputStyle.short,
                min_length=6, max_length=10,
                placeholder=trade_report.date[:100]
            ),
            disnake.ui.TextInput(
                label="Item",
                custom_id="item",
                style=disnake.TextInputStyle.short,
                placeholder=trade_report.item[:100]
            ),
            disnake.ui.TextInput(
                label="Price",
                custom_id="price",
                style=disnake.TextInputStyle.short,
                placeholder=trade_report.price[:100]
            ),
            disnake.ui.TextInput(
                label="Overpay/Underpay",
                custom_id="overpay_underpay",
                style=disnake.TextInputStyle.short,
                min_length=3, max_length=5,
                placeholder="ENTER: 'over', 'under', or 'N/A'",
            ),
            disnake.ui.TextInput(
                label="Image",
                custom_id="image_url",
                style=disnake.TextInputStyle.short,
                value=trade_report.image.url,
                placeholder="https://example.com/image.png"
            )
        ]
    )
    try:
        modal_inter: disnake.ModalInteraction = await inter.bot.wait_for(
            "modal_submit",
            check=lambda i: i.custom_id == "send_trade_report" and i.author.id == inter.author.id,
            timeout=300
        )
    except asyncio.TimeoutError:
        return await inter.author.send('Your trade report window has timed out and is no longer valid.')

    if not modal_inter.user.get_role(config.RECENT_SALES_JURY_ROLE):
        return await modal_inter.send(embed=misc.make_error(
            "No Permissions",
            f"You must have the <@&{config.RECENT_SALES_JURY_ROLE}> role to send trade reports"
        ), ephemeral=True)

    raw_overpay_underpay = modal_inter.text_values['overpay_underpay'].lower()
    overpay_underpay = raw_overpay_underpay if raw_overpay_underpay != 'n/a' else None
    
    if overpay_underpay not in ['over', 'under', None]:
        return await modal_inter.send(embed=misc.make_error(
            "Invalid Overpay/Underpay value",
            f"You entered `{overpay_underpay}`"
            " but it must be equal to `over`, `under`, or `N/A`"
        ), ephemeral=True)

    buyer_user: Optional[disnake.User] = misc.uuid_to_user(trade_report.buyer.uuid, inter.bot)
    buyer_ping = (' ' + buyer_user.mention) if buyer_user else ''
    
    seller_user: Optional[disnake.User] = misc.uuid_to_user(trade_report.seller.uuid, inter.bot)
    seller_ping = (' ' + seller_user.mention) if seller_user else ''

    censor = '||' if overpay_underpay else ''
    description = '\n'.join([
        ("# " + overpay_underpay.upper() + "PAY") if overpay_underpay else '',
        f"{censor}**Buyer:** `{trade_report.buyer.name}`{buyer_ping}",
        f"**Seller:** `{trade_report.seller.name}`{seller_ping}",
        f"**Date:** `{modal_inter.text_values['date']}`",
        f"**Item:** `{modal_inter.text_values['item']}`",
        f"**Price:** `{modal_inter.text_values['price']}`",
    ]) + censor
    embed = disnake.Embed(description=description)
    embed.set_footer(
        icon_url=modal_inter.user.display_avatar,
        text=f"Approved by {modal_inter.user.display_name}"
    )
    embed.set_image(url=modal_inter.text_values['image_url'])
    channel = inter.bot.get_channel(config.TRADE_REPORT_CHANNEL)
    exists = await log_trade_report_completion(trade_report)
    if not exists or trade_report.id in SENT_REPORTS:
        print('recieved duplicate modal response')
        # this is a duplicate interaction call
        return
    SENT_REPORTS.append(trade_report.id)
    msg = await channel.send(embed=embed)
    await inter.message.delete()
    if author:
        try:
            await author.send(f"Your trade report has been acccepted! View it at {msg.jump_url}")
        except Exception as e:
            print('error trying to dm', trade_report.author, ' - ', e)

    await modal_inter.send(embed=misc.make_success(
        "Sent Trade Report!",
        f"View it at {msg.jump_url}"
    ), ephemeral=True)


async def send_log_msg(inter: disnake.AppCmdInter, report: datatypes.TradeReport):
    channel = inter.bot.get_channel(config.TRADE_REPORT_VERIFICATION_CHANNEL)
    await channel.send()


async def report_trade_command(
    inter: disnake.AppCmdInter,
    seller_name: str,
    buyer_name: str,
    date: str,
    item: str,
    price: str,
    image: disnake.Attachment,
    notes: Optional[str]
):
    await inter.response.defer()
    if seller_name == buyer_name:
        return await inter.send(embed=misc.make_error(
            "Invalid Trade",
            "You cannot trade with yourself!"
        ))
        
    async with aiohttp.ClientSession() as session:
        seller = await mojang.get(seller_name, session=session)
        if seller is None:
            return await inter.send(embed=misc.make_error(
                "Invalid Seller",
                f"`{seller_name}` is not a valid Minecraft IGN."
            ))
        buyer = await mojang.get(buyer_name, session=session)
        if buyer is None:
            return await inter.send(embed=misc.make_error(
                "Invalid Buyer",
                f"`{buyer_name}` is not a valid Minecraft IGN."
            ))

        
        trade_report = datatypes.TradeReport(
            author=inter.user.id,
            seller=seller,
            buyer=buyer,
            date=date,
            item=item,
            price=price,
            image=await upload_image(image.proxy_url, session=session),
            notes=notes
        )
        await log_trade_report(trade_report)
        
        channel = inter.bot.get_channel(config.TRADE_REPORT_VERIFICATION_CHANNEL)
        msg = await channel.send(
            content=f"<@&{config.RECENT_SALES_JURY_ROLE}>",
            embed=trade_report.to_embed(),
            components=[
                disnake.ui.Button(
                    label="Accept",
                    style=disnake.ButtonStyle.green,
                    custom_id=f"{BUTTON_ID}|{json.dumps({'action': 'accept', 'id': trade_report.id})}"
                ),
                disnake.ui.Button(
                    label="Deny",
                    style=disnake.ButtonStyle.red,
                    custom_id=f"{BUTTON_ID}|{json.dumps({'action': 'deny', 'id': trade_report.id})}"
                )
            ]
        )
        await msg.pin()
        return await inter.send(embed=misc.make_success(
            "Success",
            "Your trade report has been sent off to server staff to be reviewed. When it is accepted or denied, you will recieve a DM."
        ))